import os
import argparse
import traceback
from collections import namedtuple, OrderedDict, defaultdict, Counter
import codecs
import json
from enum import Enum, auto

_DEFAULT_K_NORM = 5


class Text():
    CONCLUSIONS = "conclusions"
    DATABASE = "database"
    RECORD_ID = "record"
    TYPE = "type"
    CMPRESULT = "cmpresult"
    CONCLUSION_THESAURUS = "conclusionThesaurus"
    ANNOTATOR = "annotator"
    GROUPS = "groups"
    REPORTS = "reports"
    ID = "id"
    NAME = "name"
    THESAURUS_LABEL = "thesaurus"
    LANGUAGE = "language"
    ANNOTATORS = "annotators"
    CONCLUSIONS_ANNOTATORS = "conclusionsAnnotators"
    RECORDS = "records"


class MatchMarks(Enum):
    TP = auto()
    FP = auto()
    FN = auto()


class Error(Exception):
    def __init__(self, message):
        super(Error, self).__init__(message)


Thesaurus = namedtuple("Thesaurus", ["label", "lang", "items"])


InputData = namedtuple("InputData", [
    "ref_path", "test_paths", "thesaurus", "full_report", "knorm"
])


MatchStats = namedtuple("MatchStats", [
    "tp", "fp", "fn", "precision", "recall", "fscore", "norm_f"
])


CmpResult = namedtuple("CmpResult", [
    "marks_table", "stats_table", "total_stats",  # "requirement_passed"
])


def main():
    try:
        input_data = _parse_args(os.sys.argv)
        result = _compare(input_data)
        _print_report(result, input_data)
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
    parser.add_argument("--thesaurus", required=True, help="Path to thesaurus")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--knorm", default=_DEFAULT_K_NORM)
    data = parser.parse_args(args[1:])
    return InputData(
        data.ref_path,
        data.test_paths,
        _parse_thesaurus(data.thesaurus),
        data.full,
        data.knorm
    )


def _read_table(thesaurus, *paths):
    data = _read_data(*paths)
    data, _ = _filter_data(data, thesaurus)
    return _dataset_to_table(data)


def _compare(input_data):
    thesaurus_label = input_data.thesaurus.label
    ref_data = _read_table(thesaurus_label, input_data.ref_path)
    test_data = _read_table(thesaurus_label, *input_data.test_paths)
    if not ref_data or not test_data:
        raise Error("Input files not found")
    match_marks = _calculate_match_table(ref_data, test_data)
    stats_table, total_stats = _calculate_stats(match_marks, input_data.knorm)
    return CmpResult(match_marks, stats_table, total_stats)


def _print_report(result, input_data):
    _print_records_stats(result.stats_table)
    if not input_data.full_report:
        return
    _print_conclusions(result.marks_table, input_data.thesaurus.items)


def _print_records_stats(stats_table):
    for db in stats_table:
        for rec in stats_table[db]:
            stats = stats_table[db][rec]
            print(f"{db}, {rec}")
            print(f"TP: {stats.tp}")
            print(f"FP: {stats.fp}")
            print(f"FN: {stats.fn}")
            print(f"Precision: {stats.precision}")
            print(f"Recall: {stats.recall}")
            print(f"F-Score: {stats.fscore}")
            print(f"Normalized F-score: {stats.norm_f}")


def _print_conclusions(marks_table, thesaurus):
    mark_groups = defaultdict(set)
    for db_marks in marks_table.values():
        for rec_marks in db_marks.values():
            for code, mark in rec_marks.items():
                if code in thesaurus:
                    mark_groups[mark].add(code)
    codes_indices = {code: i for i, code in enumerate(thesaurus)}
    for mark, group in mark_groups.items():
        print(mark.name)
        group = sorted(group, key=(lambda code: codes_indices.get(code, 0)))
        for c in group:
            if c in thesaurus:
                print(f"  {thesaurus[c]}")


def _is_debug():
    return getattr(os.sys, 'gettrace', None) is not None


def _parse_thesaurus(filename):
    data = _read_json(filename, ordered=True)
    items = OrderedDict()
    for group in data[Text.GROUPS]:
        for ann in group[Text.REPORTS]:
            items[ann[Text.ID]] = ann[Text.NAME]
    return Thesaurus(
        data[Text.THESAURUS_LABEL],
        data[Text.LANGUAGE],
        items
    )


def _read_data(*input_paths):
    all_jsons = []
    path_not_found_fmt = "Warning! Path {0} not found."
    for path in input_paths:
        if not os.path.exists(path):
            print(path_not_found_fmt.format(path))
        elif os.path.isfile(path):
            all_jsons.append(_read_json(path))
        else:
            all_jsons += _read_json_folder(path)
    return all_jsons


def _filter_data(data, thesaurus):
    bad = []
    good = []
    for item in data:
        if item.get(Text.TYPE) == Text.CMPRESULT:
            bad.append(item)
        elif item.get(Text.CONCLUSION_THESAURUS) != thesaurus:
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


def _read_json(filename, ordered=False):
    hook = None
    if ordered:
        hook = OrderedDict
    with codecs.open(filename, "r", encoding="utf-8") as fin:
        return json.load(fin, object_pairs_hook=hook)


def _read_json_folder(dirname):
    all_paths = (os.path.join(dirname, x) for x in os.listdir(dirname))
    all_files = [p for p in all_paths
                 if os.path.isfile(p) and p.lower().endswith(".json")]
    results = []
    for fname in all_files:
        try:
            results.append(_read_json(fname))
        except ValueError:
            continue
    return results


def _calculate_match_table(ref_data, test_data):
    match_table = {}
    for db in ref_data:
        if db not in test_data:
            continue
        match_table[db] = {}
        for rec in ref_data[db]:
            if rec not in test_data[db]:
                continue
            ref_concs = set(ref_data[db][rec])
            test_concs = set(test_data[db][rec])
            all_concs = ref_concs.union(test_concs)
            marks = {}
            for code in all_concs:
                if code not in ref_concs:
                    marks[code] = MatchMarks.FP
                else:
                    if code in test_concs:
                        marks[code] = MatchMarks.TP
                    else:
                        marks[code] = MatchMarks.FN
            match_table[db][rec] = marks
    return match_table


def _calculate_stats(match_marks, knorm):
    all_marks = []
    table = {}
    for db in match_marks:
        table[db] = {}
        for rec in match_marks[db]:
            record_marks = match_marks[db][rec].values()
            table[db][rec] = _marks_to_match_stats(record_marks, knorm)
            all_marks += record_marks
    total_stats = _marks_to_match_stats(all_marks, knorm)
    return table, total_stats


def _marks_to_match_stats(marks, knorm):
    counts = Counter(marks)
    tp = counts[MatchMarks.TP]
    fp = counts[MatchMarks.FP]
    fn = counts[MatchMarks.FN]
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    fscore = 0
    if precision > 0 or recall > 0:
        fscore = 2 * precision * recall / (precision + recall)
    return MatchStats(
        tp, fp, fn, precision, recall, fscore,
        int(fscore * (knorm + 1) / knorm)
    )


if __name__ == "__main__":
    main()
