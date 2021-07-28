import os
import argparse
from collections import namedtuple, OrderedDict, defaultdict
import codecs
import json

InputData = namedtuple("InputData", ["paths", "groups", "thesaurus"])

Thesaurus = namedtuple("Thesaurus", ["label", "items", "data"])


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
    ANNOTATOR = "annotator"


def main():
    args = _parse_args()
    datatable = _read_table(args.paths, args.thesaurus.label)
    report = _create_report(datatable, args.groups, args.thesaurus.data)
    _write_report(report, "result.json")


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Select records by dianoses group")
    parser.add_argument("paths", nargs="+", help="Paths to annotation folders")
    parser.add_argument("-g", "--groups", nargs="*")
    parser.add_argument("-t", "--thesaurus", required=True)
    args = parser.parse_args()
    return InputData(args.paths, args.groups, _parse_thesaurus(args.thesaurus))


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


def _read_json(filename, ordered=False):
    hook = None
    if ordered:
        hook = OrderedDict
    with codecs.open(filename, "r", encoding="utf-8") as fin:
        return json.load(fin, object_pairs_hook=hook)


def _read_table(paths, thesaurus):
    data = _read_data(paths)
    data, _ = _filter_data(data, thesaurus)
    return _dataset_to_table(data)


def _read_data(input_paths):
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
        annotator = item[Text.ANNOTATOR]
        record = item[Text.RECORD_ID]
        table[annotator][record] = item[Text.CONCLUSIONS]
    return dict(table)


def _create_report(datatable, groups, thesaurus):
    groups = set(groups)
    group_names = OrderedDict()
    item_groups = {}
    for g in thesaurus[Text.GROUPS]:
        gid = g[Text.ID]
        gname = g[Text.NAME]
        if gid in groups:
            group_names[gid] = gname
        for c in g[Text.REPORTS]:
            cid = c[Text.ID]
            item_groups[cid] = gid

    report = {}
    for annr in datatable:
        report[annr] = OrderedDict((gname, [])
                                   for gname in group_names.values())
        for recname in datatable[annr]:
            for code in datatable[annr][recname]:
                gid = item_groups.get(code)
                if gid in groups:
                    gname = group_names[gid]
                    report[annr][gname].append(recname)
    return report


def _write_report(report, filename):
    with codecs.open(filename, "w", encoding="utf-8") as fd:
        json.dump(report, fd, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
