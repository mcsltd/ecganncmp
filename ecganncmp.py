import os
import argparse
import traceback
from collections import namedtuple, OrderedDict, defaultdict, Counter
import codecs
import json
from enum import Enum, auto
import gettext

_ = gettext.gettext

_REQURED_GROUPS = [
    set(["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7"]),
    ["3.1"]
]


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


class MatchMarks(Enum):
    TP = auto()
    FP = auto()
    FN = auto()


class Error(Exception):
    def __init__(self, message):
        super(Error, self).__init__(message)


Thesaurus = namedtuple("Thesaurus", ["label", "items", "data"])


InputData = namedtuple("InputData", [
    "ref_path", "test_paths", "thesaurus", "full_report", "knorm", "summary",
    "groups_report", "lang", "group_unions"
])


MatchStats = namedtuple("MatchStats", [
    "tp", "fp", "fn", "precision", "recall", "fscore", "norm_f"
])


CmpResult = namedtuple("CmpResult", [
    "marks_table", "stats_table", "required_group_flags", "excess_conclusions"
])


def main():
    try:
        input_data = _parse_args(os.sys.argv)
        _set_language(input_data.lang)
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


def _set_language(lang):
    global _
    obj = gettext.translation("base", localedir="locales", languages=[lang])
    obj.install()
    _ = obj.gettext


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
    parser.add_argument("-f", "--full", action="store_true",
                        help="Enable full report format")
    parser.add_argument("--knorm", type=int, default=None,
                        help="F-Score normalization factor")
    parser.add_argument("-s", "--summary", action="store_true",
                        help="Enable summary report (with average statistics)")
    parser.add_argument("-g", "--groups", action="store_true",
                        help="Enable report for conclusion groups")
    parser.add_argument("-l", "--lang", default="en", choices=["en", "ru"],
                        help="Select report language (default: %(default)s)")
    data = parser.parse_args(args[1:])
    return InputData(
        data.ref_path,
        data.test_paths,
        _parse_thesaurus(data.thesaurus),
        data.full,
        data.knorm,
        data.summary,
        data.groups,
        data.lang,
        None
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
    match_marks, excess_items = _calculate_match_table(
        ref_data, test_data, input_data.thesaurus.items,
        input_data.group_unions
    )
    stats_table = _calculate_stats(match_marks, input_data.knorm)
    required_groups_flags = _check_required_groups(test_data)
    return CmpResult(
        match_marks, stats_table, required_groups_flags, excess_items
    )


def _print_report(result, input_data):
    footer = ""
    _print_records_stats(result.stats_table, result.required_group_flags)
    if input_data.full_report:
        footer = _launch_parameters_to_str(input_data)
        _print_conclusions(result.marks_table, input_data.thesaurus.items)
        _print_excess_conclusions(result.excess_conclusions)
    if input_data.summary and _count_records(result.stats_table) > 1:
        stats = _calculate_total_stats(result.marks_table, input_data.knorm)
        _print_stats(stats, _("Summary"), 2)
    if input_data.groups_report:
        _print_groups_report(
            result.marks_table, input_data.thesaurus.data, input_data.knorm)
    if footer:
        print(footer)


def _print_records_stats(stats_table, required_groups_flags):
    for db in stats_table:
        for rec in stats_table[db]:
            title = f"{db}, {rec}"
            _print_stats(
                stats_table[db][rec], title, 2,
                required_group_missed=(not required_groups_flags[db][rec]))


def _print_conclusions(marks_table, thesaurus):
    titles = OrderedDict([
        (MatchMarks.TP, _("True")),
        (MatchMarks.FP, _("Error")),
        (MatchMarks.FN, _("Missed"))
    ])
    mark_groups = defaultdict(set)
    for db_marks in marks_table.values():
        for rec_marks in db_marks.values():
            for code, mark in rec_marks.items():
                if code in thesaurus:
                    mark_groups[mark].add(code)
    codes_indices = {code: i for i, code in enumerate(thesaurus)}
    for mark, title in titles.items():
        print(title)
        group = sorted(mark_groups[mark],
                       key=(lambda code: codes_indices.get(code, 0)))
        for c in group:
            if c in thesaurus:
                print(f"  {thesaurus[c]}")
        print("")


def _print_stats(stats, title="", indent=0, required_group_missed=False):
    padding = " " * indent
    if title:
        print(title)

    fieldnames = [
        "TP", "FP", "FN", _("Precision"), _("Recall"), _("F-Score"),
        _("Normalized F-score")
    ]
    for i, name in enumerate(fieldnames):
        value = stats[i]
        if value is not None:
            template = "{}{}: "
            if not float(value).is_integer():
                template += "{:.2f}"
            else:
                template += "{}"
            print(template.format(padding, name, value))
    if required_group_missed:
        print("{0}{1}".format(padding, _("Required group missed")))
    print("")


def _print_groups_report(marks_table, thesaurus, knorm):
    item_groups = {}
    group_names = {}
    group_marks = OrderedDict()
    for group in thesaurus[Text.GROUPS]:
        group_id = group[Text.ID]
        group_names[group_id] = group[Text.NAME]
        group_marks[group_id] = []
        for conc in group[Text.REPORTS]:
            item_groups[conc[Text.ID]] = group_id

    for db in marks_table:
        for rec in marks_table[db]:
            for code, mark in marks_table[db][rec].items():
                group = item_groups[code]
                group_marks[group].append(mark)
    for group_id in group_marks:
        if not group_marks[group_id]:
            continue
        group_stats = _marks_to_stats(group_marks[group_id], knorm)
        _print_stats(group_stats, group_names[group_id], 2)


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
        items,
        data
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


def _calculate_match_table(ref_data, test_data, thesaurus, groups=None):
    excess_items = set()
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
                if code in excess_items:
                    continue
                if code not in thesaurus:
                    excess_items.add(code)
                    continue
                other_set = None
                if code not in ref_concs:
                    marks[code] = MatchMarks.FP
                    other_set = ref_concs
                elif code in test_concs:
                    marks[code] = MatchMarks.TP
                else:
                    marks[code] = MatchMarks.FN
                    other_set = test_concs

                if groups is None or other_set is None:
                    continue
                group_id = _get_group_id(code)
                groups_union = next((g for g in groups if group_id in g), None)
                if groups_union is None:
                    continue
                if any(_get_group_id(x) in groups_union for x in other_set):
                    marks[code] = MatchMarks.TP
            match_table[db][rec] = marks
    return match_table, list(excess_items)


def _check_required_groups(test_data):
    results = {}
    for db in test_data:
        results[db] = {}
        for rec in test_data[db]:
            rec_items = test_data[db][rec]
            group_flags = [False for _ in _REQURED_GROUPS]
            for item in rec_items:
                item_group = _get_group_id(item)
                for i, groups in enumerate(_REQURED_GROUPS):
                    if group_flags[i]:
                        continue
                    group_flags[i] = item_group in groups
            results[db][rec] = all(group_flags)
    return results


def _get_group_id(conclision_id):
    last_point = conclision_id.rfind(".")
    if last_point < 0:
        return None
    return conclision_id[:last_point]


def _calculate_stats(match_marks, knorm):
    table = {}
    for db in match_marks:
        table[db] = {}
        for rec in match_marks[db]:
            record_marks = match_marks[db][rec].values()
            table[db][rec] = _marks_to_stats(record_marks, knorm)
    return table


def _calculate_total_stats(match_marks, knorm):
    all_marks = []
    for db in match_marks:
        for rec in match_marks[db]:
            all_marks += match_marks[db][rec].values()
    return _marks_to_stats(all_marks, knorm)


def _marks_to_stats(marks, knorm=None):
    counts = Counter(marks)
    tp = counts[MatchMarks.TP]
    fp = counts[MatchMarks.FP]
    fn = counts[MatchMarks.FN]
    precision = 0
    recall = 0
    fscore = 0

    if tp > 0 or fp > 0:
        precision = tp / (tp + fp)
    if tp > 0 or fn > 0:
        recall = tp / (tp + fn)
    if precision > 0 or recall > 0:
        fscore = 2 * precision * recall / (precision + recall)
    norm_fscore = None
    if knorm is not None:
        norm_fscore = int(fscore * (knorm + 1 / knorm))
    return MatchStats(tp, fp, fn, precision, recall, fscore, norm_fscore)


def _count_records(table):
    return sum(1 for db in table for _ in table[db])


def _launch_parameters_to_str(input_data):
    template = "{0}: {1}"
    lines = [_("Launch parameters")]

    if input_data.full_report:
        lines.append(_("Report format: full"))
    else:
        lines.append(_("Report format: short"))

    if input_data.knorm is not None:
        lines.append(
            template.format(_("Normalization factor"), input_data.knorm))

    yes = _("yes")
    no = _("no")

    head = _("Summary")
    tail = yes if input_data.summary else no
    lines.append(template.format(head, tail))

    head = _("Groups report")
    tail = yes if input_data.groups_report else no
    lines.append(template.format(head, tail))

    lines.append(template.format(_("Language"), input_data.lang))

    return "\n  ".join(lines)


def _print_excess_conclusions(items):
    if not items:
        return
    print(_("Items removed from comparison (not found in the thesaurus)"))
    for it in items:
        print(f"  {it}")
    print("")


def _parse_group_unions(path):
    if path is None:
        return None
    data = _read_json(path)
    return [set(x) for x in data[Text.GROUPS]]


if __name__ == "__main__":
    main()
