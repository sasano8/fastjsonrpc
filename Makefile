all: format-black format-isort test

format: format-black format-isort

format-black:
	@echo [black] && poetry run black . -v

format-isort:
	@echo [isort] && poetry run isort --profile black --filter-files .

test:
	@echo [pytest] && poetry run pytest -svx # exit instantly on first error or failed test.

test-report:
	@echo [pytest] && poetry run pytest -svx --cov # exit instantly on first error or failed test.