# -*- coding: utf-8 -*-
"""run_all.sh · .github/workflows/{update,scan}-kship.yml 회귀 (V9 docs+workflow, 2026-10-05).

네트워크·DART·레포 파일 변경 없음. 세 묶음:
  ① run_all.sh — bash 구문, --help, --print-quarter(분기말 +50일 · 사업보고서 +95일 규칙), --dry-run 의 단계 순서·네트워크 단계 제외·--only/--skip, 인자 오류.
  ② 워크플로 정적 계약 — 모든 run: 블록 bash -n, 히어독 파이썬 compile, 워크플로·run_all 이 부르는 `python3 kship_*.py --flag` 의 스크립트 존재·
     argparse 플래그 존재(문자열 리터럴), scan-kship 의 openpyxl 설치·--quarter 전달, update-kship 의 단계 제한 합 ≤ job 제한.
  ③ 워크플로 흉내 — update-kship 의 재무제표·주석·환율·게이트 run: 블록을 임시 폴더에서 가짜 python3(kship_*.py 는 기록만, `python3 -`/`-c` 는 진짜 파이썬)·
     가짜 date(요일 고정) 로 러너와 같은 셸 옵션(bash -eo pipefail) 으로 실행해 GITHUB_OUTPUT(q1·fin_changed·notes_changed·models·why) 흐름을 확인한다.
bash 가 없으면 전부 건너뛴다.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.abspath(os.path.join(TOOLS, "..", "..", ".."))
WF = os.path.join(REPO, ".github", "workflows")
UPDATE_YML = os.path.join(WF, "update-kship.yml")
SCAN_YML = os.path.join(WF, "scan-kship.yml")
RUN_ALL = os.path.join(TOOLS, "run_all.sh")
BASH = shutil.which("bash")

NETWORK_SCRIPTS = ("kship_fin.py", "kship_fx.py", "kship_price.py", "kship_contracts.py", "kship_yards.py",
                   "kship_suppliers.py", "kship_universe.py", "kship_xlsx_patch.py")

# 기대 최신 분기 — 손으로 계산한 진릿값(스크립트와 같은 코드를 베껴 쓰지 않는다): 분기말 +50일(사업보고서 +95일) 이 지난 가장 최근 분기.
QUARTER_TRUTH = (("2026-10-05", "2026Q2"), ("2026-11-18", "2026Q2"), ("2026-11-19", "2026Q3"),
                 ("2027-04-04", "2026Q3"), ("2027-04-05", "2026Q4"), ("2026-08-18", "2026Q1"), ("2026-08-19", "2026Q2"),
                 ("2026-05-19", "2025Q4"), ("2026-05-20", "2026Q1"))


def sh(args, cwd=None, env=None, timeout=120):
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def run_blocks(path):
    """워크플로의 (step name, run 본문, env 사전) 목록 — PyYAML 없이 들여쓰기로 읽는다(두 파일의 run: 은 전부 `|` 블록 또는 한 줄)."""
    lines = read(path).split("\n")
    out, i, name, env = [], 0, None, {}
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^\s*-\s*name:\s*(.*)$", ln)
        if m:
            name, env = m.group(1).strip(), {}
        m = re.match(r"^(\s*)env:\s*$", ln)
        if m and name is not None:
            ind = len(m.group(1)); j = i + 1
            while j < len(lines) and len(lines[j]) - len(lines[j].lstrip()) > ind and lines[j].strip():
                k, _, v = lines[j].strip().partition(":")
                env[k.strip()] = v.strip()
                j += 1
        m = re.match(r"^(\s*)run:\s*(\|-?|>-?)?\s*(.*)$", ln)
        if m:
            ind, style, rest = len(m.group(1)), m.group(2), m.group(3)
            if style:
                body = []; i += 1
                while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > ind):
                    body.append(lines[i]); i += 1
                out.append((name, textwrap.dedent("\n".join(body)), env))
                continue
            out.append((name, rest, env))
        i += 1
    return out


def dry_stages(text):
    """`DRY ▶ [stage] ...` 줄의 단계 이름을 등장 순서대로(중복 제거)."""
    seen = []
    for st in re.findall(r"^DRY ▶ \[(\w+)\]", text, flags=re.M):
        if st not in seen:
            seen.append(st)
    return seen


def cli_calls(text):
    """`... <script>.py --flag ...` 호출을 (script, [flags]) 로 — 히어독(`python3 -`)·`-m unittest` 는 제외."""
    calls = []
    for raw in text.split("\n"):
        line = raw.split("#", 1)[0] if not raw.lstrip().startswith("#") else ""
        toks = line.replace('"', " ").replace("'", " ").split()
        for k, t in enumerate(toks):
            if t.endswith(".py") and "/" not in t and t.startswith(("kship_", "build_dicts", "inject_link")):
                flags = []
                for u in toks[k + 1:]:
                    if u.startswith("--"):
                        flags.append(u.split("=", 1)[0])
                    elif u in ("&&", "||", "|", ";", ">", ">>", "2>&1"):
                        break
                calls.append((t, flags))
                break
    return calls


@unittest.skipUnless(BASH, "bash 없음")
class TestRunAllScript(unittest.TestCase):
    def test_exists_executable_and_syntax(self):
        self.assertTrue(os.path.isfile(RUN_ALL), RUN_ALL)
        self.assertTrue(os.access(RUN_ALL, os.X_OK), "chmod +x tools/run_all.sh")
        r = sh([BASH, "-n", RUN_ALL])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_help(self):
        r = sh([BASH, RUN_ALL, "--help"])
        self.assertEqual(r.returncode, 0, r.stderr)
        for flag in ("--dry-run", "--print-quarter", "--net", "--patch", "--only", "--skip", "--today", "--quarter"):
            self.assertIn(flag, r.stdout)

    def test_print_quarter_rule(self):
        for today, want in QUARTER_TRUTH:
            r = sh([BASH, RUN_ALL, "--print-quarter", "--today", today])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), want, today)
        r = sh([BASH, RUN_ALL, "--print-quarter", "--quarter", "2026Q3"])          # --quarter 가 규칙을 덮는다
        self.assertEqual(r.stdout.strip(), "2026Q3")

    def test_dry_run_default_is_offline_in_contract_order(self):
        r = sh([BASH, RUN_ALL, "--dry-run"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(dry_stages(r.stdout), ["sls", "model", "pages", "link", "tests", "check"])
        for s in NETWORK_SCRIPTS:
            self.assertNotIn(s, r.stdout, "기본 실행에 네트워크 단계가 섞였다: %s" % s)
        self.assertIn("kship_sls.py --all --report", r.stdout)
        self.assertIn("kship_model.py --build --all --xlsx", r.stdout)
        self.assertRegex(r.stdout, r"kship_page\.py --all[\s\S]*kship_parts\.py --all[\s\S]*kship_model_section\.py --hub[\s\S]*inject_link\.py --apply")
        self.assertIn("unittest discover -s tests -p test_*.py", r.stdout)

    def test_dry_run_net_patch_order_and_arguments(self):
        ref = tempfile.mkdtemp(prefix="kship_ref_"); self.addCleanup(shutil.rmtree, ref, True)   # 레퍼런스 폴더가 '있는' 경우 — patch 단계가 켜진다
        env = dict(os.environ, KSHIP_REF_DIR=ref)
        r = sh([BASH, RUN_ALL, "--dry-run", "--net", "--patch", "--today", "2026-10-05", "--quarter", "2026Q3"], env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(dry_stages(r.stdout),
                         ["collect", "fin", "notes", "market", "sls", "model", "patch", "pages", "link", "tests", "check"])
        self.assertIn("kship_fin.py --collect --all --quarters 2021Q4..2026Q3", r.stdout)
        self.assertIn("kship_fin.py --collect-notes --all --notes-parent-fallback", r.stdout)
        self.assertIn("kship_yards.py --collect --quarter 2026Q3", r.stdout)
        self.assertIn("kship_suppliers.py --collect --quarter 2026Q3", r.stdout)
        self.assertIn("kship_model.py --build --all --xlsx --today 2026-10-05", r.stdout)
        self.assertIn("kship_fx.py --today 2026-10-05", r.stdout)
        self.assertIn("kship_xlsx_patch.py --all --verify --overwrite-placeholders --fx-actuals --is-convention 3m --today 2026-10-05 --ref-dir " + ref,
                      r.stdout)
        # collect 가 fin 보다, market 이 sls 보다, model 이 pages 보다 앞(MODEL.md §7 의 순서 계약)
        pos = {s: r.stdout.index("DRY ▶ [%s]" % s) for s in ("collect", "fin", "market", "sls", "model", "pages")}
        self.assertLess(pos["collect"], pos["fin"]); self.assertLess(pos["market"], pos["sls"]); self.assertLess(pos["model"], pos["pages"])

    def test_patch_skipped_without_reference_dir(self):
        r = sh([BASH, RUN_ALL, "--only", "patch"], env=dict(os.environ, KSHIP_REF_DIR="/nonexistent/ref_dir_for_test"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("레퍼런스 폴더 없음", r.stdout)
        self.assertNotIn("▶ [patch] ", r.stdout.replace("· [patch]", ""))

    def test_only_and_skip(self):
        r = sh([BASH, RUN_ALL, "--dry-run", "--only", "sls,model"])
        self.assertEqual(dry_stages(r.stdout), ["sls", "model"])
        r = sh([BASH, RUN_ALL, "--dry-run", "--skip", "tests,link"])
        self.assertEqual(dry_stages(r.stdout), ["sls", "model", "pages", "check"])

    def test_argument_errors_exit_2(self):
        for args in (["--quarter", "2026Q5"], ["--only", "bogus", "--dry-run"], ["--wat"], ["--today", "2026-13-01", "--print-quarter"], ["--today"]):
            r = sh([BASH, RUN_ALL] + args)
            self.assertEqual(r.returncode, 2, (args, r.stdout, r.stderr))


@unittest.skipUnless(BASH, "bash 없음")
class TestWorkflowStatic(unittest.TestCase):
    def test_run_blocks_bash_syntax_and_python_heredocs(self):
        n = 0
        for path in (UPDATE_YML, SCAN_YML):
            blocks = run_blocks(path)
            self.assertGreaterEqual(len(blocks), 3, path)
            for name, body, _env in blocks:
                with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as f:
                    f.write(body); p = f.name
                try:
                    r = sh([BASH, "-n", p])
                finally:
                    os.unlink(p)
                self.assertEqual(r.returncode, 0, "%s · %s: %s" % (os.path.basename(path), name, r.stderr))
                for src in re.findall(r"<<'PY'\n(.*?)\nPY", body, flags=re.S):
                    compile(textwrap.dedent(src), "%s:%s" % (os.path.basename(path), name), "exec")
                n += 1
        self.assertGreaterEqual(n, 14)

    def test_cli_flags_exist_in_tools(self):
        """워크플로·run_all 이 부르는 스크립트와 --플래그가 tools/ 의 argparse 정의(문자열 리터럴)에 있다."""
        texts = [read(RUN_ALL)] + [body for path in (UPDATE_YML, SCAN_YML) for _n, body, _e in run_blocks(path)]
        seen = set()
        for text in texts:
            for script, flags in cli_calls(text):
                sp = os.path.join(TOOLS, script)
                self.assertTrue(os.path.isfile(sp), "스크립트 없음: %s" % script)
                src = read(sp)
                for fl in flags:
                    self.assertTrue('"%s"' % fl in src or "'%s'" % fl in src, "%s 에 %s 정의 없음" % (script, fl))
                    seen.add((script, fl))
        for must in (("kship_fin.py", "--quarters"), ("kship_fin.py", "--collect-notes"), ("kship_fin.py", "--notes-parent-fallback"),
                     ("kship_scan.py", "--quarter"), ("kship_model.py", "--xlsx"), ("kship_sls.py", "--report"), ("kship_xlsx_patch.py", "--is-convention")):
            self.assertIn(must, seen)

    def test_update_workflow_step_timeouts_fit_job_timeout(self):
        text = read(UPDATE_YML)
        job = int(re.search(r"^    timeout-minutes:\s*(\d+)", text, flags=re.M).group(1))
        steps = re.split(r"\n      - ", text)
        fin = next(s for s in steps if "\n        id: fin\n" in "\n" + s)
        notes = next(s for s in steps if "\n        id: notes\n" in "\n" + s)
        tf = int(re.search(r"timeout-minutes:\s*(\d+)", fin).group(1))
        tn = int(re.search(r"timeout-minutes:\s*(\d+)", notes).group(1))
        self.assertGreaterEqual(job, tf + tn + 30, "job %d < fin %d + notes %d + 30" % (job, tf, tn))
        self.assertIn("continue-on-error: true", fin); self.assertIn("continue-on-error: true", notes)

    def test_update_workflow_cache_save_condition_and_commit_excludes(self):
        text = read(UPDATE_YML)
        self.assertIn("steps.fin.outputs.fin_changed != 'false' || steps.notes.outputs.notes_changed != 'false'", text)
        self.assertIn("':(exclude)argus/kship/tools/assets/fin_cache'", text)
        self.assertIn("mkdir -p assets/fin_cache", text)                       # 89f95231 — 첫 실행(캐시 없음) 에서 listing 이 죽지 않게
        self.assertNotIn("git add -A", text)

    def test_scan_workflow_installs_openpyxl_and_passes_quarter(self):
        text = read(SCAN_YML)
        self.assertIn("openpyxl==3.1.5", text)                                # tests 가 모듈 수준에서 openpyxl 을 import 한다
        self.assertRegex(text, r'kship_scan\.py --scan --quarter "\$Q1"')
        self.assertIn('python-version: "3.11"', text)
        self.assertNotIn("git add -A", text)
        self.assertIn("-p 'test_*.py'", text)


@unittest.skipUnless(BASH, "bash 없음")
class TestWorkflowSimulated(unittest.TestCase):
    """update-kship 의 run: 블록을 가짜 python3·date 로 흉내낸다(러너와 같은 `bash -eo pipefail`)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kship_wf_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin"); os.makedirs(self.bin)
        self.work = os.path.join(self.tmp, "argus", "kship", "tools"); os.makedirs(os.path.join(self.work, "assets"))
        self.log = os.path.join(self.tmp, "stub.log"); self.gh_out = os.path.join(self.tmp, "gh_output")
        self._stub("python3", r'''#!/usr/bin/env bash
if [ "${1:-}" = "-" ] || [ "${1:-}" = "-c" ]; then exec "$REAL_PY" "$@"; fi
printf '%s\n' "$*" >> "$STUB_LOG"
case " $* " in
  *" --collect "*|*" --collect-notes "*)
    if [ "${STUB_CREATE:-0}" = "1" ]; then mkdir -p assets/fin_cache/stub; printf x > "assets/fin_cache/stub/$RANDOM$RANDOM.html"; fi ;;
esac
exit 0
''')
        self._stub("date", r'''#!/usr/bin/env bash
if [ "$*" = "-u +%u" ] && [ -n "${FAKE_DOW:-}" ]; then echo "$FAKE_DOW"; exit 0; fi
exec /bin/date "$@"
''')
        if not shutil.which("sha256sum"):
            self._stub("sha256sum", '#!/usr/bin/env bash\nexec shasum -a 256 "$@"\n')
        self.blocks = {name: (body, env) for name, body, env in run_blocks(UPDATE_YML)}

    def _stub(self, name, body):
        p = os.path.join(self.bin, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        os.chmod(p, 0o755)

    def _block(self, key):
        name = next(n for n in self.blocks if n and n.startswith(key))
        return self.blocks[name][0]

    def _run(self, key, cwd=None, create=False, **extra):
        body = self._block(key)
        p = os.path.join(self.tmp, re.sub(r"\W+", "_", key) + ".sh")
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), REAL_PY=sys.executable,
                   STUB_LOG=self.log, GITHUB_OUTPUT=self.gh_out, STUB_CREATE="1" if create else "0", TODAY="2026-10-05",
                   PYTHONDONTWRITEBYTECODE="1")
        env.update({k: str(v) for k, v in extra.items()})
        return sh([BASH, "-eo", "pipefail", p], cwd=cwd or self.work, env=env)

    def _outputs(self):
        # 맥 기본 bash 3.2 는 `"$VAR·…"` 처럼 변수 확장 바로 뒤의 멀티바이트 글자(U+00B7 ·)의 선두 바이트를 떨어뜨린다(실측 — 러너의 bash 5 는 정상).
        # 그래서 깨진 바이트는 대체해 읽고, 단언은 · 가 없는 조각으로만 한다.
        out = {}
        if os.path.exists(self.gh_out):
            with open(self.gh_out, encoding="utf-8", errors="replace") as f:
                for ln in f.read().splitlines():
                    k, _, v = ln.partition("="); out[k] = v
        return out

    def _log(self):
        return read(self.log) if os.path.exists(self.log) else ""

    def test_fin_step_first_run_rebuilds_and_requeries_latest_two_quarters(self):
        cache = os.path.join(self.work, "assets", "fin_cache", "000001"); os.makedirs(cache)
        for q in ("2026Q2", "2026Q1", "2025Q4"):
            with open(os.path.join(cache, "%s_meta.json" % q), "w", encoding="utf-8") as f:
                f.write('{"rcp": null}')
        with open(os.path.join(cache, "2025Q3_meta.json"), "w", encoding="utf-8") as f:
            f.write('{"rcp": "20251114000001"}')
        r = self._run("Financial statements", create=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self._outputs()
        self.assertEqual(out.get("q1"), "2026Q2", out)                  # TODAY=2026-10-05 → 분기말 +50일 규칙
        self.assertEqual(out.get("fin_changed"), "true", out)
        log = self._log()
        self.assertIn("kship_fin.py --collect --all --quarters 2021Q4..2026Q2", log)
        self.assertIn("kship_fin.py --build --all --quarters 2021Q4..2026Q2", log)
        self.assertLess(log.index("--collect --all"), log.index("--build --all"))
        # '보고서 없음' meta 는 최신 2분기만 지운다 — 2025Q4 의 rcp null 과 2025Q3 의 실제 접수는 그대로
        left = sorted(os.listdir(cache))
        self.assertEqual(left, ["2025Q3_meta.json", "2025Q4_meta.json"], left)
        self.assertIn("재탐색할 '보고서 없음' meta: 2", r.stdout)

    def test_fin_step_unchanged_cache_keeps_fin_json(self):
        os.makedirs(os.path.join(self.work, "assets", "fin_cache", "x"))
        with open(os.path.join(self.work, "assets", "fin_cache", "x", "a.html"), "w") as f:
            f.write("x")
        os.makedirs(os.path.join(self.work, "assets", "fin"))
        with open(os.path.join(self.work, "assets", "fin", "010140.json"), "w") as f:
            f.write("{}")
        r = self._run("Financial statements", create=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._outputs().get("fin_changed"), "false")
        self.assertNotIn("--build --all", self._log())
        self.assertIn("캐시 변경 없음", r.stdout)

    def test_fin_step_without_cache_dir_does_not_die(self):
        """89f95231 — 캐시 복원이 비어 assets/fin_cache 가 없어도 listing 에서 죽지 않는다."""
        r = self._run("Financial statements", create=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._outputs().get("fin_changed"), "true")     # fin json 이 없으니 재생성 분기

    def test_fin_step_quarter_input_validation(self):
        r = self._run("Financial statements", QUARTER_INPUT="2026Q3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._outputs().get("q1"), "2026Q3")
        r = self._run("Financial statements", QUARTER_INPUT="2026-Q3")
        self.assertEqual(r.returncode, 2)

    def test_notes_step_outputs(self):
        r = self._run("Financial statement notes", create=False, Q1="2026Q2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._outputs().get("notes_changed"), "false")
        self.assertIn("kship_fin.py --collect-notes --all --notes-parent-fallback", self._log())
        self.assertNotIn("--build", self._log())
        os.unlink(self.gh_out); os.unlink(self.log)
        r = self._run("Financial statement notes", create=True, Q1="2026Q2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._outputs().get("notes_changed"), "true")
        self.assertIn("kship_fin.py --build --all --quarters 2021Q4..2026Q2", self._log())

    def test_market_step_carries_history_only_with_previous_commit(self):
        r = self._run("FX and prices")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = self._log()
        self.assertLess(log.index("kship_fx.py"), log.index("kship_price.py"))
        self.assertIn("직전 prices.json 없음", r.stdout)                  # 레포 밖에선 이어붙임을 건너뛴다(예외 → SystemExit 0)

    def test_gate_step_reasons(self):
        r = self._run("Decide whether", cwd=self.tmp, FAKE_DOW="2", MODELS_INPUT="", FIN_CHANGED="true", NOTES_CHANGED="false")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self._outputs(); self.assertEqual(out.get("models"), "true"); self.assertIn("재무 변경", out.get("why", "")); self.assertIn("summary.json 없음", out.get("why", ""))
        os.makedirs(os.path.join(self.work, "assets", "models")); open(os.path.join(self.work, "assets", "models", "summary.json"), "w").write("{}")
        os.unlink(self.gh_out)
        r = self._run("Decide whether", cwd=self.tmp, FAKE_DOW="2", MODELS_INPUT="", FIN_CHANGED="false", NOTES_CHANGED="false")
        out = self._outputs(); self.assertEqual(out.get("models"), "false", out); self.assertIn("평일", out.get("why", "")); self.assertIn("변경 없음", out.get("why", ""))
        os.unlink(self.gh_out)
        r = self._run("Decide whether", cwd=self.tmp, FAKE_DOW="1", MODELS_INPUT="", FIN_CHANGED="false", NOTES_CHANGED="false")
        out = self._outputs(); self.assertEqual(out.get("models"), "true"); self.assertEqual(out.get("why"), "월요일")
        os.unlink(self.gh_out)
        r = self._run("Decide whether", cwd=self.tmp, FAKE_DOW="3", MODELS_INPUT="true", FIN_CHANGED="", NOTES_CHANGED="true")
        out = self._outputs(); self.assertIn("수동 입력", out.get("why", "")); self.assertIn("주석 변경", out.get("why", "")); self.assertNotIn("재무 변경", out.get("why", ""))

    def test_models_and_pages_steps_order(self):
        r = self._run("SLS · models")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self._run("Pages")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = self._log()
        order = ["kship_sls.py --all --report", "kship_model.py --build --all --xlsx", "kship_page.py --all", "kship_parts.py --all",
                 "kship_model_section.py --hub", "inject_link.py --apply"]
        idx = [log.index(s) for s in order]
        self.assertEqual(idx, sorted(idx), log)


if __name__ == "__main__":
    unittest.main()
