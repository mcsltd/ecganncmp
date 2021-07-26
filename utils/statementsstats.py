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


InputData = namedtuple("InputData", ["ref_path", "test_paths", "thesaurus"])


Thesaurus = namedtuple("Thesaurus", ["label", "items"])


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
        result = _compare(input_data)
        _write_report(result, input_data)
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
    data = parser.parse_args(args[1:])
    return InputData(
        data.ref_path,
        data.test_paths,
        _parse_thesaurus(data.thesaurus),
    )


def _parse_thesaurus(filename):
    data = _read_json(filename, ordered=True)
    items = OrderedDict()
    for group in data[Text.GROUPS]:
        for ann in group[Text.REPORTS]:
            items[ann[Text.ID]] = ann[Text.NAME]
    return Thesaurus(data[Text.THESAURUS_LABEL], items)


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
    marks = _compare_statements(ref_data, test_data)
    return _count_marks(marks)


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


def _compare_statements(ref_data, test_data):
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
                mark = None
                if code not in ref_concs:
                    mark = MatchMarks.FP
                elif code in test_concs:
                    mark = MatchMarks.TP
                else:
                    mark = MatchMarks.FN
                marks[code].append(mark)
    return dict(marks)


def _count_marks(all_marks):
    return {code: dict(Counter(marks)) for code, marks in all_marks.items()}


def _write_report(result, input_data, filename="report.xlsx"):
    thesaurus = input_data.thesaurus.items
    table = pandas.DataFrame(columns=MatchMarks)
    for code, text in thesaurus.items():
        code_marks = result.get(code)
        if code_marks is None:
            continue
        table.loc[text] = code_marks
    ref_annotator = os.path.basename(input_data.ref_path)
    test_annotators = map(os.path.basename, input_data.test_paths)
    table = table.sort_index(axis=1).fillna(0).rename(columns={
        MatchMarks.TP: "Оба",
        MatchMarks.FP: "Только " + ", ".join(test_annotators),
        MatchMarks.FN: "Только " + ref_annotator
    })
    table.to_excel(filename)


def _print_warning(text):
    os.sys.stderr.write("Warning! {0}\n".format(text))


def _marks_to_stats(marks):
    tp = marks.get(MatchMarks.TP, 0)
    fp = marks.get(MatchMarks.FP, 0)
    fn = marks.get(MatchMarks.FN, 0)
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


if __name__ == "__main__":
    main()
