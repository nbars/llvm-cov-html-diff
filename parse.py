from pathlib import Path
from bs4 import BeautifulSoup
import bs4
from IPython import embed
from dataclasses import dataclass
from typing import List, Optional, Set
import re
import shutil
import dataclasses
import json

class JsonDataclass:

    def json(self):
        return dataclasses.asdict(self) # type: ignore

@dataclass(unsafe_hash=True)
class CoverageMetricValues(JsonDataclass):
    covered: int
    total: int


@dataclass(unsafe_hash=True)
class CoverageMercies(JsonDataclass):
    function_cov: CoverageMetricValues
    line_cov: CoverageMetricValues
    region_cov: CoverageMetricValues
    branch_cov: CoverageMetricValues


@dataclass(unsafe_hash=True)
class FileCoverageSummary(JsonDataclass):
    name: Path
    summary: CoverageMercies


@dataclass(unsafe_hash=True)
class TotalCoverageSummary(JsonDataclass):
    summary: CoverageMercies


class ParsedLLVMCovReport:

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

        self._parse_index()

    def name(self) -> str:
        return self._name

    def report_root(self) -> Path:
        return self._root

    def index_covered_files(self) -> List[FileCoverageSummary]:
        return self._coverage_summary_files

    def indexed_files(self) ->Set[str]:
        return { file.name.as_posix() for file in self.index_covered_files()}

    def index_covered_files_totals(self) -> TotalCoverageSummary:
        return self._coverage_summary_totals

    def _parse_index(self):
        parsed = BeautifulSoup(self._index.read_text(), "html.parser")
        tables = parsed.find_all("table")
        assert len(tables) == 2

        coverage_table = tables[0]
        files_without_function_table = tables[1]

        files, footer = coverage_table = ParsedLLVMCovReport._parse_coverage_table(
            coverage_table
        )
        self._coverage_summary_files = files
        self._coverage_summary_totals = footer

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
            values = [col.text for col in row.find_all("td")]
            filename = values[0]

            # skip file name
            col_values = values[1:]
            # parse the (6/48) part
            covered_vs_total_re = r".*\(([0-9]+)/([0-9]+)\)"
            covered_vs_total_col = [re.match(covered_vs_total_re, value) for value in col_values]  # type: ignore

            coverd_vs_total_col_values = []
            for value in covered_vs_total_col:
                if value is None:
                    raise ValueError(f"Error while parsing row of file {filename}")
                # value[0] contains whole match
                coverd_vs_total_col_values.append((int(value[1]), int(value[2])))

            function_cov = CoverageMetricValues(
                coverd_vs_total_col_values[0][0], coverd_vs_total_col_values[0][1]
            )
            line_cov = CoverageMetricValues(
                coverd_vs_total_col_values[1][0], coverd_vs_total_col_values[1][1]
            )
            region_cov = CoverageMetricValues(
                coverd_vs_total_col_values[2][0], coverd_vs_total_col_values[2][1]
            )
            branch_cov = CoverageMetricValues(
                coverd_vs_total_col_values[3][0], coverd_vs_total_col_values[3][1]
            )

            cov_summary = CoverageMercies(
                function_cov, line_cov, region_cov, branch_cov
            )
            if filename != "Totals":
                file_summary = FileCoverageSummary(Path(filename), cov_summary)
                file_summaries.append(file_summary)
            else:
                footer = TotalCoverageSummary(cov_summary)

        if footer is None:
            raise ValueError("Report does not contain a 'Totals' row")

        return (file_summaries, footer)
