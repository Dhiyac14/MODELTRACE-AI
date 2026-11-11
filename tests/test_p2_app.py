"""Person 2: the Streamlit dashboard renders every section and drives the approval workflow."""
import json
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from inventory.registry import save_inventory, seed_records
from workflow.approvals import load_users
from workflow.state_machine import Workflow

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ["Executive Overview", "Discovery", "Documentation", "Migration", "Validation",
            "Risk & Evidence", "Monitoring", "Governance"]
USER_INDEX = {"dev.alex": 0, "val.sam": 1, "mrm.jordan": 2, "mon.riley": 3, "lead.taylor": 4}


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """A private copy of the data the app reads, so tests never touch the real governance logs."""
    for rel in ("governance/users.json", "governance/ss1_23_mapping.json",
                "reports/discovery/legacy-r-logistic_discovery.json", "tests/fixtures/p2"):
        src, dest = ROOT / rel, tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest) if src.is_dir() else shutil.copy(src, dest)
    (tmp_path / "inventory").mkdir()
    save_inventory(seed_records(), tmp_path / "inventory/model_inventory.json")
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("MODELTRACE_ROOT", str(tmp_path))
    for name in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL"):  # never call a real LLM from tests
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def app(section, model="legacy-r-logistic", user="dev.alex", samples=False) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.session_state["section"] = section
    at.session_state["model"] = model
    at.session_state["user"] = USER_INDEX[user]
    at.session_state["samples"] = samples
    return at.run()


@pytest.mark.parametrize("samples", [False, True])
@pytest.mark.parametrize("section", SECTIONS)
def test_every_section_renders(data_root, section, samples):
    at = app(section, samples=samples)
    assert not at.exception
    sample_banners = [w for w in at.warning if "SAMPLE DATA" in w.value]
    uses_person1_data = section in ("Migration", "Validation", "Monitoring")
    assert bool(sample_banners) == (samples and uses_person1_data)


def test_python_model_has_no_redevelopment(data_root):
    at = app("Migration", model="python-gradient-boosting")
    assert any("already implemented in Python" in i.value for i in at.info)


def test_submit_and_approve_through_the_ui(data_root):
    at = app("Discovery", user="dev.alex")
    assert at.button(key="approve-legacy-r-logistic-discover").disabled  # nothing submitted, and wrong role
    at.button(key="submit-legacy-r-logistic-discover").click().run()
    assert not at.exception and any("submitted for review" in s.value for s in at.success)

    at = app("Discovery", user="mrm.jordan")
    at.button(key="approve-legacy-r-logistic-discover").click().run()
    assert any("'Approve' recorded" in s.value for s in at.success)

    records = json.loads((data_root / "governance/approval_log.json").read_text())
    assert [(r["action"], r["actor"]) for r in records] == [("submit", "dev.alex"), ("approve", "mrm.jordan")]
    inventory = json.loads((data_root / "inventory/model_inventory.json").read_text())
    assert inventory[0]["tier_status"] == "approved" and inventory[0]["lifecycle_stage"] == "document"

    at = app("Governance", user="mrm.jordan")
    assert any("Audit chain intact: 2 events" in s.value for s in at.success)


def test_sample_data_cannot_satisfy_a_gate(data_root):
    users = {u.user_id: u for u in load_users(data_root / "governance/users.json")}
    wf = Workflow(data_root)
    card = wf.artifacts.path("model_card", "legacy-r-logistic")
    card.parent.mkdir(parents=True)
    card.write_text("{}")
    for stage in ("discover", "document"):
        wf.submit("legacy-r-logistic", stage, users["dev.alex"])
        wf.decide("legacy-r-logistic", stage, users["mrm.jordan"], "approve")

    at = app("Migration", user="dev.alex", samples=True)
    assert any("Parity tests passed" in s.value for s in at.success)  # the sample says passed...
    assert at.button(key="submit-legacy-r-logistic-redevelop").disabled          # ...but it is not live evidence
    assert any("No evidence yet: reports/migration/migration_results.json" in m.value for m in at.markdown)


def test_documentation_agent_runs_from_the_ui(data_root):
    at = app("Documentation", user="dev.alex")
    at.button(key="run-docs").click().run()
    assert not at.exception
    card = json.loads((data_root / "reports/documentation/legacy-r-logistic_model_card.json").read_text())
    assert card["generated_by"] == "Documentation Agent (template, no LLM)"
    events = json.loads((data_root / "governance/audit_log.json").read_text())
    assert events[-1]["actor"] == "agent:documentation" and events[-1]["details"]["triggered_by"] == "dev.alex"
