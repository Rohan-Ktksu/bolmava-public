"""Print a Markdown summary of JUnit XML reports (pytest --junitxml) for $GITHUB_STEP_SUMMARY. Standard library only."""
import sys
import xml.etree.ElementTree as ET

failed_any = False
for path in sys.argv[1:]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        print(f"### {path}\n\nNo report ({e}). The step probably failed before tests ran.\n")
        failed_any = True
        continue
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = sum(int(s.get("tests", 0)) for s in suites)
    failures = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    seconds = sum(float(s.get("time", 0)) for s in suites)
    print(f"### {path.rsplit('/', 1)[-1]}\n\n**{total - failures - skipped} passed, {failures} failed, {skipped} skipped** in {seconds:.1f} s\n")
    for case in root.iter("testcase"):
        for problem in [*case.findall("failure"), *case.findall("error")]:
            failed_any = True
            first = (problem.get("message") or problem.text or "").strip().splitlines()[:1]
            print(f"- `{case.get('classname')}::{case.get('name')}`: {first[0][:300] if first else problem.tag}")
    print()
sys.exit(0)  # the test step itself fails the job; this script only reports
