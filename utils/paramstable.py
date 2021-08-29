import argparse
import os
import traceback
import codecs
import json
from collections import namedtuple, OrderedDict, defaultdict
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
    ANNOTATOR = "annotator"


class Error(Exception):
    def __init__(self, message):
        super(Error, self).__init__(message)


Thesaurus = namedtuple("Thesaurus", ["label", "items",  "ann_groups"])


InputData = namedtuple("InputData", [
    "ref_anns", "test_anns", "thesaurus", "measures", "paramsgroups", "output"
])


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


def _is_debug():
    return getattr(os.sys, 'gettrace', None) is not None


def _parse_args(args):
    parser = argparse.ArgumentParser(description="Annotations comparing")
    parser.add_argument(
        "ref_anns", help="Path to file or folder with reference annotaions")
    parser.add_argument(
        "test_anns", nargs="+",
        help="Path to file or folder with test annotations"
    )
    parser.add_argument("-o", "--output", default="result.xlsx")
    required_named_args = parser.add_argument_group("required named arguments")
    required_named_args.add_argument(
        "-t", "--thesaurus", required=True, help="Path to thesaurus")
    required_named_args.add_argument(
        "-m", "--measures", required=True
    )
    required_named_args.add_argument(
        "-g", "--paramsgroups", required=True
    )
    data = parser.parse_args(args[1:])
    return InputData(
        data.ref_anns,
        data.test_anns,
        data.thesaurus,
        data.measures,
        data.paramsgroups,
        data.output
    )


def _parse_thesaurus(filename):
    data = _read_json(filename, ordered=True)
    items = OrderedDict()
    ann_groups = OrderedDict()
    for group in data[Text.GROUPS]:
        for ann in group[Text.REPORTS]:
            ann_id = ann[Text.ID]
            items[ann_id] = ann[Text.NAME]
            ann_groups[ann_id] = group[Text.ID]
    return Thesaurus(
        data[Text.THESAURUS_LABEL],
        items,
        ann_groups
    )


def _read_json(filename, ordered=False):
    hook = None
    if ordered:
        hook = OrderedDict
    with codecs.open(filename, "r", encoding="utf-8") as fin:
        return json.load(fin, object_pairs_hook=hook)


def _compare(input_data):
    input_data = _read_input_data(input_data)
    return _create_params_table(input_data)


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
    table = {}
    for item in dataset:
        record = item[Text.RECORD_ID]
        table[record] = item[Text.CONCLUSIONS]
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


def _print_warning(text):
    os.sys.stderr.write("Warning! {0}\n".format(text))


def _read_input_data(input_data):
    error_message = "Input files not found"
    thesaurus = _parse_thesaurus(input_data.thesaurus)
    thesaurus_label = thesaurus.label
    ref_data = _read_table(thesaurus_label, input_data.ref_anns)
    test_data = _read_test_table(thesaurus_label, *input_data.test_anns)
    if not ref_data or not test_data:
        raise Error(error_message)
    return InputData(
        ref_data, test_data, thesaurus,
        _read_json(input_data.measures),
        _read_json(input_data.paramsgroups, ordered=True),
        input_data.output
    )


def _read_test_table(thesaurus, *paths):
    data = _read_data(*paths)
    data, _ = _filter_data(data, thesaurus)
    table = defaultdict(dict)
    for item in data:
        record = item[Text.RECORD_ID]
        annotator = item[Text.ANNOTATOR]
        table[record][annotator] = item[Text.CONCLUSIONS]
    return dict(table)


def _create_params_table(input_data):
    qtc_param = "QTc"
    thesaurus = input_data.thesaurus.items
    anns_order = dict((c, i) for i, c in enumerate(thesaurus))
    result_table = {}
    for rec in input_data.ref_anns:
        if rec not in input_data.test_anns:
            continue
        record_row = OrderedDict()
        ann_groups = set()
        for param in input_data.paramsgroups:
            ann_groups.update(input_data.paramsgroups[param])
            record_row[param] = _get_param_value(
                input_data.measures, rec, param)
            if param == "QT":
                record_row[qtc_param] = _get_param_value(
                    input_data.measures, rec, qtc_param)
        anns = OrderedDict()
        anns["Ref"] = input_data.ref_anns[rec]
        anns.update(input_data.test_anns[rec])
        for annotr in anns:
            params_anns = _select_group_anns(
                anns[annotr], ann_groups, input_data.thesaurus.ann_groups)
            if not params_anns:
                record_row[annotr] = ""
                continue
            params_anns.sort(key=anns_order.get)
            record_row[annotr] = "\n".join(
                thesaurus[c] for c in params_anns)
        result_table[rec] = record_row
    return result_table


def _get_param_value(measures, record, param_id):
    params = measures.get(record)
    return params[param_id] if params is not None else "-"


def _select_group_anns(anns, groups, ann_groups):
    result = []
    for ann in anns:
        group = ann_groups.get(ann)
        if group in groups:
            result.append(ann)
    return result


def _write_report(result, input_data):
    pandas.DataFrame.from_dict(
        result, orient="index").to_excel(input_data.output)


if __name__ == "__main__":
    main()
