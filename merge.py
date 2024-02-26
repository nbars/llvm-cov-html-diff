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

from parse import (
    CoverageMetricValue,
    ParsedHtmlLLVMCovReport,
    JsonDataclass,
    FileCoverageSummary,
)


@dataclass(unsafe_hash=True)
class MaterializedFileCoverageSummary(JsonDataclass):
    rel_src_path: str
    report_name: str
    function_cov: CoverageMetricValue
    line_cov: CoverageMetricValue
    region_cov: CoverageMetricValue
    branch_cov: CoverageMetricValue

    @staticmethod
    def from_file_coverage_summary(
        report_name: str, o: FileCoverageSummary
    ) -> "MaterializedFileCoverageSummary":
        return MaterializedFileCoverageSummary(
            o.src_relative_path.as_posix(),
            report_name,
            o.summary.function_cov,
            o.summary.line_cov,
            o.summary.region_cov,
            o.summary.branch_cov,
        )


class MergeReports:
    COVERAGE_FILES_FOLDER = Path("coverage")

    def __init__(
        self, reports: List[ParsedHtmlLLVMCovReport], merged_outout: Path
    ) -> None:
        self._reports = reports
        self._out_dir = merged_outout.resolve()
        if self._out_dir.exists():
            raise FileExistsError(f"Output dir {self._out_dir} already exists")
        self._out_dir.mkdir(parents=True)

        self._render_style()
        self._render_index()
        self._render_file_reports()

    @staticmethod
    def _get_jinja_env():
        jinja_env = Environment(
            loader=PackageLoader("main"),
            autoescape=select_autoescape(),
            block_start_string="{%",
            block_end_string="%}",
            variable_start_string='"@{',
            variable_end_string='}@"',
        )
        return jinja_env

    def unique_relative_src_files_path(self) -> list[str]:
        files = [
            set(report.covered_files_relative_src_path()) for report in self._reports
        ]
        files = list(reduce(lambda a, b: a | b, files, set()))  # type: ignore
        files.sort()
        return files

    def _render_style(self):
        jinja_env = MergeReports._get_jinja_env()
        style_template = jinja_env.get_template("style.css")
        rendered_style = style_template.render()
        self._style_css_path = self._out_dir / "style.css"
        self._style_css_path.write_text(rendered_style)

    def _render_file_reports(self):
        jinja_env = MergeReports._get_jinja_env()
        file_template = jinja_env.get_template("file.html")

        file_reports_dir = self._out_dir / MergeReports.COVERAGE_FILES_FOLDER
        file_reports_dir.mkdir()

        rel_src_files_path = self.unique_relative_src_files_path()
        for rel_src_path in rel_src_files_path:
            dst_path = file_reports_dir / rel_src_path
            dst_path = dst_path.parent / f"{dst_path.name}.html"
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            style_css_path = (
                Path(
                    len(dst_path.parent.relative_to(self._style_css_path.parent).parts)
                    * "../"
                )
                / "style.css"
            )
            rendered = file_template.render(
                style_css_path=style_css_path,
                coverage_a_name=json.dumps(self._reports[0].name()),
                coverage_b_name=json.dumps(self._reports[1].name()),
                coverage_a=self._reports[0].file_coverage(rel_src_path).json(),
                coverage_b=self._reports[1].file_coverage(rel_src_path).json(),
            )
            dst_path.write_text(rendered)

    def _render_index(self):
        jinja_env = MergeReports._get_jinja_env()
        index_template = jinja_env.get_template("index.html")

        # All files that are listed in at least in one report
        rel_src_paths = self.unique_relative_src_files_path()

        # All report names
        report_names = [report.name() for report in self._reports]
        report_names.sort()

        indexed_files = []
        for report in self._reports:
            for file in report.covered_files_summaries():
                indexed_files.append(
                    MaterializedFileCoverageSummary.from_file_coverage_summary(
                        report.name(), file
                    ).json()
                )

        rendered_index = index_template.render(
            files=rel_src_paths, report_names=report_names, indexed_files=indexed_files
        )
        index_file = self._out_dir / "index.html"
        index_file.write_text(rendered_index)
