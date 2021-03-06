# ecganncmp

The program is used to compare annotation files obtained as a result of processing a set of ECG records. Annotation to databases are available on ecg.ru. An explanatory note and a description of the comparison method are given in the [document](https://ws.mks.ru/#preview-185656-ecganncmp-docx) and in the [another](https://ws.mks.ru/#preview-185247-docx).

## Resources

Professional tool for physicians and biomedical engineers  
https://ecg.ru/

## Usage

Python (3.4 or later) must be installed on the user's computer to run the program. The program accepts file with annotaion thesaurus, two path to reference and test files or folders with annotations. The formats of the input files are described [there](https://github.com/mcsltd/ecganncompare/blob/master/docs/formats.md). The launch is done through the command line as shown below.

    $ python ecganncmp.py ref_path test_path --thesaurus=path/to/thesaurus.json

`ref_path`, `test_path` and `--thesaurus` are required arguments. Optional arguments and short description are given below (help message)

    usage: ecganncmp.py [-h] -t THESAURUS [-f] [--knorm KNORM] [-s] [-g]
                        [-l {en,ru}] [-u GROUP_UNIONS]
                        ref_path test_paths [test_paths ...]

    Annotations comparing

    positional arguments:
    ref_path              Path to file or folder with reference annotaions
    test_paths            Path to file or folder with test annotations

    optional arguments:
    -h, --help            show this help message and exit
    -f, --full            Enable full report format
    --knorm KNORM         F-Score normalization factor
    -s, --summary         Enable summary report (with average statistics)
    -g, --groups          Enable report for conclusion groups
    -l {en,ru}, --lang {en,ru}
                            Select report language (default: en)
    -u GROUP_UNIONS, --group_unions GROUP_UNIONS
                            Path to file with group unions

    required named arguments:
    -t THESAURUS, --thesaurus THESAURUS
                            Path to thesaurus

See below for arguments details.

## Output examples

The following [terms](https://en.wikipedia.org/wiki/Confusion_matrix) are used when comparing annotations:
- TP &ndash; true positive,  
- FP &ndash; false positive,
- FN &ndash; false negative,
- Precision &ndash; positive predictive value, 

        RRV = TP / (TP + FP),

- Recall &ndash; sensitivity or true positive rate, 

        TPR = TP / (TP + FN).

Also used the `F-score` or `F` &ndash; total score of annotations match,  

    F = (2 * Precision * Recall) / (Precision + Recall).

If the `--knorm` flag is set, the normalized F-score is calculated:

    NFS = round((knorm + 1 / knorm) * F)

### Group unions

In command line arguments, you can specify a file with groups for comparison. Statements from the same group are considered conditionally equal.
So TP &ndash; (true positive) used when statements belong to the same group.


### Main report

The main (default) report displays information on each considered annotation (record), includes:
- record identifier;
- the number of statements of each type TP, FP, FN;
- Precision;
- Recall;
- F-score;
- flag of absence of conclusions on required groups;
- normalized F-score, if necessary.

Report example:

    CSE Common Standards for ECG, MA1_007
      TP: 2
      FP: 0
      FN: 1
      Precision: 1.0
      Recall: 0.67
      F-Score: 0.80
      Normalized F-score: 4

### Full report

If the `--full` or `-f` flag is set, launch flags and a list of statements grouped by type (TP, FP, FN) are added to the report.  
Subheadings:
- TP &ndash; True.
- FP &ndash; Error.
- FN &ndash; Missed.

### Summary report

The summary report can be output only when comparing sets of annotation. If the `--summary` or `-s` flag is set at startup, then the following are displayed:
- total values of TP, FP, FN;
- Precision and Recall calculated for total TP, FP, FN;
- F-score (normalized, if necessary) calculated for total Precision and Recall.

Summary report example:

    TP: 109
    FP: 314
    FN: 282
    Precision: 0.26
    Recall: 0.28
    F-Score: 0.27

### Groups report

If the `--groups` or `-g` flag is specified, then in the order of the groups, the following information is displayed:
- group identifier;
- TP, FP, FN, Precision, Recall, F-Score calculated for this group.
