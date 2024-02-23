from pathlib import Path
from bs4 import BeautifulSoup
import bs4
from IPython import embed
from dataclasses import dataclass
from typing import List, Optional
import re
import shutil

from parse import ParsedLLVMCovReport
from merge import MergeReports


def main():
    report_a = Path(
        "test_reports/ft-mosquitto-pub_mosquitto_1-86400s-1_report/html-report"
    )
    report_b = Path(
        "test_reports/sgfuzz-mosquitto-pub_mosquitto_1-86400s-1_results/html-report"
    )

    report_a = ParsedLLVMCovReport("FT", report_a)
    report_b = ParsedLLVMCovReport("SGFuzz", report_b)

    out_dir = Path("out_report")
    shutil.rmtree(out_dir, ignore_errors=True)
    MergeReports([report_a, report_b], out_dir)

if __name__ == "__main__":
    main()
