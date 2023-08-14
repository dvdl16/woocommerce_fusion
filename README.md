## WooCommerce Fusion

WooCommerce connector for ERPNext v14+

#### License

Dirk van der Laarse

#### Tests

To run unit tests:

```shell
bench --site test_site run-tests --app woocommerce_fusion --coverage
```

#### Development

We use [pre-commit](https://pre-commit.com/) for linting. First time setup may be required:
```shell
# Install pre-commit
pip install pre-commit

# Install the git hook scripts
pre-commit install

#(optional) Run against all the files
pre-commit run --all-files
```

We use [Semgrep](https://semgrep.dev/docs/getting-started/) rules specific to [Frappe Framework](https://github.com/frappe/frappe)
```shell
# Install semgrep
python3 -m pip install semgrep

# Clone the rules repository
git clone --depth 1 https://github.com/frappe/semgrep-rules.git frappe-semgrep-rules

# Run semgrep specifying rules folder as config 
python3 -m semgrep --config=/workspace/development/frappe-semgrep-rules/rules apps/woocommerce_fusion
```

If you use VS Code, you can specify the `.flake8` config file in your `settings.json` file:
```shell
"python.linting.flake8Args": ["--config=frappe-bench-v14/apps/woocommerce_fusion/.flake8_strict"]
```
```