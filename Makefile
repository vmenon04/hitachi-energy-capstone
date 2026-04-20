.PHONY: clean badge

badge:
	@pip install anybadge --quiet
	@python -c "\
import xml.etree.ElementTree as ET, anybadge, os; \
os.makedirs('docs/badges', exist_ok=True); \
pct = round(float(ET.parse('coverage.xml').getroot().attrib['line-rate']) * 100, 1); \
color = 'green' if pct >= 70 else ('yellow' if pct >= 50 else 'red'); \
anybadge.Badge('coverage', f'{pct}%', default_color=color).write_badge('docs/badges/coverage.svg', overwrite=True); \
print(f'Coverage badge: {pct}% ({color})')\
"

clean:
	find . -type d \( -name "htmlcov" -o -name ".pytest_cache" -o -name "__pycache__" \) -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -f .coverage coverage.xml