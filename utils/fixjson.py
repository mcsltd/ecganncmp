import codecs
import os
import json


def main():
    dirpath = os.path.abspath(os.sys.argv[1])
    for fname in os.listdir(dirpath):
        fpath = os.path.join(dirpath, fname)
        text = None
        with codecs.open(fpath, "r", encoding="utf-8") as fin:
            text = fin.read()
        try:
            _ = json.loads(text)
            continue
        except ValueError:
            pass
        if text.endswith("\\"):
            text += "\\"
        text += '"}'
        obj = json.loads(text)
        with codecs.open(fpath, "w", encoding="utf-8") as fd:
            json.dump(obj, fd, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
