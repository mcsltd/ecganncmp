import argparse
import codecs
import json
import os
from collections import namedtuple, OrderedDict, defaultdict
import traceback
from enum import IntEnum, auto
from typing import Counter
import pandas


class Text():
    CONCLUSIONS = "conclusions"
    DATABASE = "database"
    RECORD_ID = "record"
    TYPE = "type"
    CONCLUSION_THESAURUS = "conclusionThesaurus"
    GROUPS = "groups"
    REPORTS = "reports"
    ID = "id"
    NAME = "name"
    THESAURUS_LABEL = "thesaurus"


InputData = namedtuple(
    "InputData", ["ref_path", "test_paths", "thesaurus", "group_unions"])


Thesaurus = namedtuple("Thesaurus", ["label", "items", "data", "groups"])


class MatchMarks(IntEnum):
    TP = auto()
    FN = auto()
    FP = auto()


class Error(Exception):
    def __init__(self, message):
        super(Error, self).__init__(message)


def main():
    try:
        input_data = _parse_args(os.sys.argv)
        code_marks = _compare(input_data)
        thesaurus = input_data.thesaurus
        if input_data.group_unions is None:
            table = _create_statements_table(code_marks, thesaurus.items)
        else:
            table = _create_groups_table(
                code_marks, thesaurus.data, input_data.group_unions)
        _write_report(table)
    except Error as exc:
        print("Error: {0}\n".format(exc))
    except Exception as exc:
        if _is_debug():
            raise
        log_filename = "errors-log.txt"
        message = "Fatal error! {0}: {1}. See details in file '{2}'."
        print(message.format(type(exc).__name__, exc, log_filename))
        with open(log_filename, "wt") as log:
            log.write(traceback.format_exc())


def _parse_args(args):
    parser = argparse.ArgumentParser(description="Annotations comparing")
    parser.add_argument(
        "ref_path", help="Path to file or folder with reference annotaions")
    parser.add_argument(
        "test_paths", nargs="+",
        help="Path to file or folder with test annotations"
    )
    required_group = parser.add_argument_group("required named arguments")
    required_group.add_argument(
        "-t", "--thesaurus", required=True, help="Path to thesaurus")
    parser.add_argument("-u", "--group_unions",
                        help="Path to file with group unions")
    data = parser.parse_args(args[1:])
    return InputData(
        data.ref_path,
        data.test_paths,
        _parse_thesaurus(data.thesaurus),
        _parse_group_unions(data.group_unions)
    )


def _parse_thesaurus(filename):
    data = _read_json(filename, ordered=True)
    items = OrderedDict()
    groups = {}
    for group in data[Text.GROUPS]:
        for ann in group[Text.REPORTS]:
            ann_id = ann[Text.ID]
            items[ann_id] = ann[Text.NAME]
            groups[ann_id] = group[Text.ID]
    return Thesaurus(data[Text.THESAURUS_LABEL], items, data, groups)


def _read_json(filename, ordered=False):
    hook = None
    if ordered:
        hook = OrderedDict
    with codecs.open(filename, "r", encoding="utf-8") as fin:
        return json.load(fin, object_pairs_hook=hook)


def _is_debug():
    return getattr(os.sys, 'gettrace', None) is not None


def _compare(input_data):
    thesaurus_label = input_data.thesaurus.label
    ref_data = _read_table(thesaurus_label, input_data.ref_path)
    test_data = _read_table(thesaurus_label, *input_data.test_paths)
    if not ref_data or not test_data:
        raise Error("Input files not found")
    return _compare_statements(ref_data, test_data, input_data.thesaurus,
                               input_data.group_unions)


def _read_table(thesaurus, *paths):
    data = _read_data(*paths)
    data, _ = _filter_data(data, thesaurus)
    return _dataset_to_table(data)


def _read_data(*input_paths):
    all_jsons = []
    path_not_found_fmt = "Path {0} not found."
    for path in input_paths:
        if not os.path.exists(path):
            _print_warning(path_not_found_fmt.format(path))
        elif os.path.isfile(path):
            all_jsons.append(_read_json(path))
        else:
            all_jsons += _read_json_folder(path)
    return all_jsons


def _filter_data(data, thesaurus):
    bad = []
    good = []
    for item in data:
        bad_item = (
            Text.CONCLUSIONS not in item or
            item.get(Text.CONCLUSION_THESAURUS) != thesaurus
        )
        if bad_item:
            bad.append(item)
        else:
            good.append(item)
    return good, bad


def _dataset_to_table(dataset):
    table = defaultdict(dict)
    for item in dataset:
        database = item[Text.DATABASE]
        record = item[Text.RECORD_ID]
        table[database][record] = item[Text.CONCLUSIONS]
    return dict(table)


def _read_json_folder(dirname):
    cannot_read_fmt = "Cannot read file: {0}"
    all_paths = (os.path.join(dirname, x) for x in os.listdir(dirname))
    all_files = [p for p in all_paths
                 if os.path.isfile(p) and p.lower().endswith(".json")]
    results = []
    for fname in all_files:
        try:
            results.append(_read_json(fname))
        except ValueError:
            _print_warning(cannot_read_fmt.format(os.path.abspath(fname)))
            continue
    return results


def _compare_statements(ref_data, test_data, thesaurus, group_unions=None):
    excess_items = set()
    marks = defaultdict(list)
    for db in ref_data:
        if db not in test_data:
            continue
        for rec in ref_data[db]:
            if rec not in test_data[db]:
                continue
            ref_concs = set(ref_data[db][rec])
            test_concs = set(test_data[db][rec])
            all_concs = ref_concs.union(test_concs)
            for code in all_concs:
                if code in excess_items:
                    continue
                if code not in thesaurus.items:
                    excess_items.add(code)
                    continue
                other_set = None
                if code not in ref_concs:
                    mark = MatchMarks.FP
                    other_set = ref_concs
                elif code in test_concs:
                    mark = MatchMarks.TP
                else:
                    mark = MatchMarks.FN
                    other_set = test_concs
                marks[code].append(mark)

                if group_unions is None or other_set is None:
                    continue
                group_id = thesaurus.groups[code]
                _, groups_union = _select_group_union(group_id, group_unions)
                if groups_union is None:
                    continue
                if any(thesaurus.groups[x] in groups_union for x in other_set):
                    marks[code][-1] = MatchMarks.TP
    return marks


def _write_report(table, filename="report.xlsx"):
    table.astype(float).round(3).to_excel(filename)


def _print_warning(text):
    os.sys.stderr.write("Warning! {0}\n".format(text))


def _marks_to_stats(marks):
    counts = Counter(marks)
    tp = counts.get(MatchMarks.TP, 0)
    fp = counts.get(MatchMarks.FP, 0)
    fn = counts.get(MatchMarks.FN, 0)
    precision = 0
    recall = 0
    fscore = 0

    if tp > 0 or fp > 0:
        precision = tp / (tp + fp)
    if tp > 0 or fn > 0:
        recall = tp / (tp + fn)
    if precision > 0 or recall > 0:
        fscore = 2 * precision * recall / (precision + recall)

    result = OrderedDict()
    result["TP"] = tp
    result["FP"] = fp
    result["FN"] = fn
    result["Precision"] = precision
    result["Recall"] = recall
    result["F-score"] = fscore
    result["F-score-5"] = _normalize_score(fscore, 5)
    result["F-score-100"] = _normalize_score(fscore, 100)
    return result


def _normalize_score(score, k):
    return round(score * (k + 1 / k))


def _parse_group_unions(path):
    if path is None:
        return None
    data = _read_json(path)
    return {k: set(v) for k, v in data[Text.GROUPS].items()}


def _select_group_union(group_id, unions):
    return next((gu for gu in unions.items()
                 if group_id in gu[1]), (None, None))


def _create_statements_table(code_marks, thesaurus):
    table = None
    for code, text in thesaurus.items():
        marks = code_marks.get(code)
        if marks is None:
            continue
        stats = _marks_to_stats(marks)
        if table is None:
            table = pandas.DataFrame(columns=stats.keys())
        table.loc[text] = stats
    return table


def _create_groups_table(code_marks, thesaurus, unions=None):
    item_groups = {}
    group_marks = OrderedDict()
    for gname in thesaurus[Text.GROUPS]:
        group_id = gname[Text.ID]
        union_name = None
        if unions is not None:
            union_name, _ = _select_group_union(group_id, unions)
        name = union_name or gname[Text.NAME]
        group_marks[name] = []
        for conc in gname[Text.REPORTS]:
            item_groups[conc[Text.ID]] = name

    for code, marks in code_marks.items():
        gname = item_groups[code]
        group_marks[gname] += marks

    table = None
    for gname in group_marks:
        if not group_marks[gname]:
            continue
        stats = _marks_to_stats(group_marks[gname])
        if table is None:
            table = pandas.DataFrame(columns=stats.keys())
        table.loc[gname] = stats
    return table


if __name__ == "__main__":
    main()
