.PHONY: doctor lint-phase0 test-phase0 test-phase1a test-phase1 test-phase2 test-phase3 test-phase4 test-phase5 test-phase6 test-phase7 test-phase8 test-phase9 test-phase10 test-phase11 test-phase12 test-phase13 test-phase14 test-phase15 test-phase16

doctor:
	bash scripts/doctor.sh

lint-phase0:
	bash scripts/lint_phase0.sh

test-phase0:
	python3 -m unittest discover -s tests/unit -p "test_phase0_*.py"

test-phase1a:
	python3 -m unittest discover -s tests/unit -p "test_phase1a_*.py"

test-phase1:
	python3 -m unittest discover -s tests/unit -p "test_phase1_*.py"

test-phase2:
	python3 -m unittest discover -s tests/unit -p "test_phase2_*.py"

test-phase3:
	python3 -m unittest discover -s tests/unit -p "test_phase3_*.py"

test-phase4:
	python3 -m unittest discover -s tests/unit -p "test_phase4_*.py"

test-phase5:
	python3 -m unittest discover -s tests/unit -p "test_phase5_*.py"

test-phase6:
	python3 -m unittest discover -s tests/unit -p "test_phase6_*.py"

test-phase7:
	python3 -m unittest discover -s tests/unit -p "test_phase7_*.py"

test-phase8:
	python3 -m unittest discover -s tests/unit -p "test_phase8_*.py"

test-phase9:
	python3 -m unittest discover -s tests/unit -p "test_phase9_*.py"

test-phase10:
	python3 -m unittest discover -s tests/unit -p "test_phase10_*.py"

test-phase11:
	python3 -m unittest discover -s tests/unit -p "test_phase11_*.py"

test-phase12:
	python3 -m unittest discover -s tests/unit -p "test_phase12_*.py"

test-phase13:
	python3 -m unittest discover -s tests/unit -p "test_phase13_*.py"

test-phase14:
	python3 -m unittest discover -s tests/unit -p "test_phase14_*.py"

test-phase15:
	python3 -m unittest discover -s tests/unit -p "test_phase15_*.py"

test-phase16:
	python3 -m unittest discover -s tests/unit -p "test_phase16_*.py"
