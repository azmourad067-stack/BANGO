from bongo.cli import main
from bongo.setup_check import MISSING, OK, run_checks


def test_programme(capsys, root, monkeypatch):
    monkeypatch.chdir(root)
    assert main(["programme"]) == 0
    assert "frog, leaf" in capsys.readouterr().out


def test_check_script_example(capsys, root, monkeypatch, tmp_path):
    monkeypatch.chdir(root)
    out_json = tmp_path / "qa.json"
    assert main(["check-script", "content/examples/ep003_frog_leaf.json", "--json", str(out_json)]) == 0
    assert "Épisode 3 : OK" in capsys.readouterr().out
    assert out_json.is_file()


def test_check_script_missing_file(capsys, root, monkeypatch):
    monkeypatch.chdir(root)
    assert main(["check-script", "absent.json"]) == 1
    assert "Erreur" in capsys.readouterr().err


def test_outside_project(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BONGO_ROOT", raising=False)
    assert main(["programme"]) == 1
    assert "dossier du projet" in capsys.readouterr().err


def test_build_week_bad_start(capsys, root, monkeypatch):
    monkeypatch.chdir(root)
    assert main(["build-week", "--start", "2026-12-02"]) == 1
    err = capsys.readouterr().err
    assert "2026-12-01" in err and "2026-12-08" in err
    assert main(["build-week", "--start", "demain"]) == 1


def test_placeholders_then_check_setup(capsys, project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("BONGO_ROOT", raising=False)
    assert main(["placeholders"]) == 0
    checks = {c.name: c for c in run_checks(project)}
    assert checks["Programme"].status == OK
    assert checks["Assets « jungle »"].status == OK
    assert checks["Police"].status == OK
    main(["check-setup"])
    assert "Vérification de l'installation" in capsys.readouterr().out


def test_check_setup_reports_missing_assets(project):
    checks = {c.name: c for c in run_checks(project)}
    assert checks["Assets « jungle »"].status == MISSING
    assert "placeholders" in checks["Assets « jungle »"].fix


def test_compile_arguments(capsys, root, monkeypatch):
    from bongo.compile import default_title
    from bongo.curriculum import load_curriculum

    monkeypatch.chdir(root)
    assert main(["compile"]) == 1
    assert "--week" in capsys.readouterr().err
    assert main(["compile", "--week", "2026-12-03"]) == 1
    c = load_curriculum(root)
    assert default_title(c, 1, 7) == "Bongo's Week in the Jungle"
    assert default_title(c, 6, 8) == "Bongo's Adventures, Episodes 6 to 8"
