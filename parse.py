from pathlib import Path
from bs4 import BeautifulSoup
import bs4
from IPython import embed
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple, Union
import re
import shutil
import dataclasses
import json
from collections import namedtuple
from multiprocessing import Pool


class JsonDataclass:

    def _value_to_json(self, v):
        if isinstance(v, JsonDataclass):
            return v.json()
        elif isinstance(v, Path):
            return v.as_posix()
        elif isinstance(v, list):
            new_list = []
            for e in v:
                new_list.append(self._value_to_json(e))
            return new_list
        elif isinstance(v, dict):
            for k1, v1 in v.items():
                v[k1] = self._value_to_json(v1)
            return v
        elif v is None:
            return "null"
        else:
            return v

    def json(self):
        ret = {}
        for k,v in dataclasses.asdict(self).items():  # type: ignore
            ret[k] = self._value_to_json(v)
        return ret
@dataclass(unsafe_hash=True)
class CoverageMetricValue(JsonDataclass):
    covered: int
    total: int


@dataclass(unsafe_hash=True)
class CoverageMercies(JsonDataclass):
    function_cov: CoverageMetricValue
    line_cov: CoverageMetricValue
    region_cov: CoverageMetricValue
    branch_cov: CoverageMetricValue


@dataclass(unsafe_hash=True)
class FileCoverageSummary(JsonDataclass):
    # Path to the corresponding source file relative to the project root.
    # E.g., include/some_name.h or lib/some_name.c
    src_relative_path: Path
    # Path to the detailed html report for this file relative to index.html.
    # E.g., coverage/home/user/..../some_name.html
    html_report_path: Path
    # The mercies for the file.
    summary: CoverageMercies


@dataclass(unsafe_hash=True)
class TotalCoverageSummary(JsonDataclass):
    summary: CoverageMercies


@dataclass(unsafe_hash=True)
class UncoveredLineRegion(JsonDataclass):
    start_col: int
    length: int


@dataclass(unsafe_hash=True)
class FileLine(JsonDataclass):
    line: int
    exec_cnt: Optional[int]
    text: str
    uncovered_regions: List[UncoveredLineRegion]


@dataclass(unsafe_hash=True)
class FileCoverage(JsonDataclass):
    src_relative_path: Path
    absolute_source_file_path: Path
    lines: List[FileLine]


class ParsedHtmlLLVMCovReport:

    def __init__(self, name: str, root: Path) -> None:
        self._root = root
        self._name = name
        if not self._root.exists():
            raise FileNotFoundError(f"The folder {self._root} does not exist.")

        self._index = root / "index.html"
        self._style = root / "style.css"
        self._coverage_dir = root / "coverage"

        for file in [self._index, self._style, self._coverage_dir]:
            if not file.exists():
                raise FileNotFoundError(
                    f"Missing '{file}', are you sure that this is an html LLVM coverage report?"
                )

        self._parse()

    def name(self) -> str:
        """
        The user defined name of this report.
        """
        return self._name

    def report_root(self) -> Path:
        """
        The root folder of this coverage report (i.e., the folder where index.html is located)
        """
        return self._root

    def covered_files_summaries(self) -> List[FileCoverageSummary]:
        """
        Coverage summary for each file that was covered.
        """
        return self._coverage_summaries

    def covered_files_relative_src_path(self) -> Set[str]:
        """
        Paths of all files that have been covered.
        """
        return {
            file.src_relative_path.as_posix() for file in self.covered_files_summaries()
        }

    def covered_files_summary_total(self) -> TotalCoverageSummary:
        """
        Summary of coveage stats computed over all covered files.
        """
        return self._coverage_summaries_total

    def file_coverage(self, src_rel_path: Union[Path, str]) -> FileCoverage:
        if isinstance(src_rel_path, str):
            src_rel_path = Path(src_rel_path)
        files = self.covered_files_coverage()
        for f in files:
            if f.src_relative_path == src_rel_path:
                return f
        assert False

    def covered_files_coverage(self) -> List[FileCoverage]:
        return self._file_coverage

    def _parse(self):
        # Parse the index table
        parsed = BeautifulSoup(self._index.read_text(), "html.parser")
        tables = parsed.find_all("table")
        assert len(tables) == 2

        coverage_table = tables[0]
        files_without_function_table = tables[1]

        files, footer = coverage_table = ParsedHtmlLLVMCovReport._parse_coverage_table(
            coverage_table
        )
        self._coverage_summaries = files
        self._coverage_summaries_total = footer

        # Parse each source file report
        file_coverage_reports = []

        pool = Pool()
        file_paths = [
            (file.src_relative_path, self.report_root() / file.html_report_path)
            for file in self._coverage_summaries
        ]

        file_coverage_reports = [
            report for report in pool.starmap(self._parse_file_report, file_paths)
        ]

        self._file_coverage = file_coverage_reports

    @staticmethod
    def _parse_file_row(row) -> FileLine:
        idx, exec_cnt, text = row
        idx = int(idx.text)

        # Parse the exec cnt
        exec_cnt = exec_cnt.text
        if exec_cnt != "":
            exec_cnt_re = r"([0-9\.]+)(.*)"
            exec_cnt_match = re.match(exec_cnt_re, exec_cnt)
            assert exec_cnt_match
            groups = exec_cnt_match.groups()

            exec_cnt = float(groups[0])
            suffix = groups[1]
            if suffix == "":
                pass
            elif suffix == "k":
                exec_cnt *= 1000
            elif suffix == "M":
                exec_cnt *= 1_000_000
            else:
                raise AssertionError(f"Unknown exec cnt suffix: {suffix}")
            exec_cnt = int(exec_cnt)
        else:
            # Line that can not be executed, e.g., comments.
            exec_cnt = None

        uncovered_regions: List[UncoveredLineRegion] = []

        # parse uncovered regions if any
        if text.find(attrs={"class": "red"}):
            text = text.find("pre")

            # the line contains at least one uncovered segment
            current_col = 0
            raw_regions = list(text.children)

            for region in raw_regions:
                if isinstance(region, bs4.element.Tag) and region.get("class") == ["red"]:
                    red_region_len = len(region.text)
                    uncov_region = UncoveredLineRegion(current_col, red_region_len)
                    uncovered_regions.append(uncov_region)
                    current_col += red_region_len
                else:
                    current_col += len(region.text)

        return FileLine(idx, exec_cnt, text.text, uncovered_regions)

    @staticmethod
    def _parse_file_report(relativ_src_path: Path, report_path: Path) -> FileCoverage:
        parser = BeautifulSoup(report_path.read_text(), "html.parser")

        title_tag = parser.find(attrs={"class": "source-name-title"})
        assert title_tag
        absolute_src_file_path = Path(title_tag.text)

        rows = []
        source_rows_raw = parser.find_all("tr")

        lines = []

        # skip header row
        for row in source_rows_raw[1:]:
            values = row.find_all("td")
            assert len(values) == 3
            line = ParsedHtmlLLVMCovReport._parse_file_row(row)
            lines.append(line)

        return FileCoverage(relativ_src_path, absolute_src_file_path, lines)

    @staticmethod
    def _parse_coverage_table(
        coverage_table: bs4.element.Tag,
    ) -> tuple[list[FileCoverageSummary], TotalCoverageSummary]:
        rows = coverage_table.find_all("tr")
        if len(rows) < 1:
            raise ValueError("Summary table contains no table header")
        header: bs4.element.Tag = rows[0]
        rows: List[bs4.element.Tag] = rows[1:]

        headings: List[str] = [heading.text for heading in header.find_all("td")]
        expected_headings = [
            "Filename",
            "Function Coverage",
            "Line Coverage",
            "Region Coverage",
            "Branch Coverage",
        ]
        if headings != expected_headings:
            raise ValueError(
                f"Summary table has unexpected headings. Expected: {expected_headings}. Got: {headings}"
            )

        file_summaries: List[FileCoverageSummary] = []
        footer: Optional[TotalCoverageSummary] = None

        for row in rows:
            values = [col for col in row.find_all("td")]

            values_text = [value.text for value in values]
            src_relative_path = values_text[0]

            if src_relative_path != "Totals":
                html_report_path = Path(values[0].find("a")["href"])
            else:
                html_report_path = None

            # skip file name col
            col_values = values_text[1:]
            # parse the (6/48) part
            covered_vs_total_re = r".*\(([0-9]+)/([0-9]+)\)"
            covered_vs_total_col = [re.match(covered_vs_total_re, value) for value in col_values]  # type: ignore

            coverd_vs_total_col_values = []
            for value in covered_vs_total_col:
                if value is None:
                    raise ValueError(
                        f"Error while parsing row of file {src_relative_path}"
                    )
                # value[0] contains whole match
                coverd_vs_total_col_values.append((int(value[1]), int(value[2])))

            function_cov = CoverageMetricValue(
                coverd_vs_total_col_values[0][0], coverd_vs_total_col_values[0][1]
            )
            line_cov = CoverageMetricValue(
                coverd_vs_total_col_values[1][0], coverd_vs_total_col_values[1][1]
            )
            region_cov = CoverageMetricValue(
                coverd_vs_total_col_values[2][0], coverd_vs_total_col_values[2][1]
            )
            branch_cov = CoverageMetricValue(
                coverd_vs_total_col_values[3][0], coverd_vs_total_col_values[3][1]
            )

            cov_summary = CoverageMercies(
                function_cov, line_cov, region_cov, branch_cov
            )
            if src_relative_path != "Totals":
                assert html_report_path
                file_summary = FileCoverageSummary(
                    Path(src_relative_path), html_report_path, cov_summary
                )
                file_summaries.append(file_summary)
            else:
                footer = TotalCoverageSummary(cov_summary)

        if footer is None:
            raise ValueError("Report does not contain a 'Totals' row")

        return (file_summaries, footer)
