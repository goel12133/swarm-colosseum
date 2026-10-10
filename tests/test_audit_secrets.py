"""The audit's personal-email and identity checks (launch, 2026-10-10). Synthetic strings only."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audit_secrets", ROOT / "scripts" / "audit_secrets.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_consumer_mail_addresses_are_flagged_and_project_ones_are_not():
    rx = audit.PERSONAL_EMAIL
    # built from pieces so no address-shaped string is ever committed (the audit would flag it)
    for user, domain in (("someone.x", "gmail.com"), ("a_b", "Outlook.com"), ("x", "proton.me"),
                         ("y", "icloud.com")):
        bad = user + "@" + domain
        assert rx.search(bad), bad
    for ok in ("130884359+goel12133@users.noreply.github.com", "dev@swarm-colosseum.invalid",
               "league@localhost", "r@r"):
        assert not rx.search(ok), ok


def test_project_identities_come_from_public_identity():
    own = audit.project_identities()
    public = (ROOT / "scripts" / "public_identity").read_text().splitlines()[1].strip()
    assert public in own and "league@localhost" in own
    assert not any(e.startswith("root@") for e in own)
