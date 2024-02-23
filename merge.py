from pathlib import Path
from bs4 import BeautifulSoup
import bs4
from IPython import embed
from dataclasses import dataclass
from typing import List, Optional
import re
import shutil
from jinja2 import Environment, PackageLoader, select_autoescape
import json
from functools import reduce
from collections import defaultdict

from parse import CoverageMetricValues, ParsedLLVMCovReport, JsonDataclass, FileCoverageSummary

@dataclass(unsafe_hash=True)
class MaterializedFileCoverageSummary(JsonDataclass):
    file_name: str
    report_name: str
    function_cov: CoverageMetricValues
    line_cov: CoverageMetricValues
    region_cov: CoverageMetricValues
    branch_cov: CoverageMetricValues

    @staticmethod
    def from_file_coverage_summary(report_name: str, o: FileCoverageSummary) -> 'MaterializedFileCoverageSummary':
        return MaterializedFileCoverageSummary(o.name.as_posix(), report_name, o.summary.function_cov, o.summary.line_cov, o.summary.region_cov, o.summary.branch_cov)



class MergeReports:

    def __init__(self, reports: List[ParsedLLVMCovReport], merged_outout: Path) -> None:
        self._reports = reports
        self._out_dir = merged_outout
        if self._out_dir.exists():
            raise FileExistsError(f"Output dir {self._out_dir} already exists")
        self._out_dir.mkdir(parents=True)

        self._render_style()
        self._render_index()

    @staticmethod
    def _get_jinja_env():
        jinja_env = Environment(
            loader=PackageLoader("main"),
            autoescape=select_autoescape(),
            block_start_string="{%",
            block_end_string="{%",
            variable_start_string="@{",
            variable_end_string="}@"

        )
        return jinja_env

    def _render_style(self):
        jinja_env = MergeReports._get_jinja_env()
        style_template = jinja_env.get_template("style.css")
        rendered_style = style_template.render()
        style_path = self._out_dir / "style.css"
        style_path.write_text(rendered_style)

    def _render_index(self):
        jinja_env = MergeReports._get_jinja_env()
        index_template = jinja_env.get_template("index.html")

        # All files that are listed in at least in one report
        files = [set(report.indexed_files()) for report in self._reports]
        files = list(reduce(lambda a, b: a | b, files, set()))
        files.sort()

        # All report names
        report_names = [report.name() for report in self._reports]
        report_names.sort()

        indexed_files = []
        for report in self._reports:
            for file in report.index_covered_files():
                indexed_files.append( MaterializedFileCoverageSummary.from_file_coverage_summary(report.name(), file).json())

        rendered_index = index_template.render(files=files, report_names=report_names, indexed_files=indexed_files)
        index_file = self._out_dir / "index.html"
        index_file.write_text(rendered_index)