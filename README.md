## WooCommerce Fusion

![CI workflow](https://github.com/dvdl16/woocommerce_fusion/actions/workflows/ci.yml/badge.svg?branch=version-15)
[![codecov](https://codecov.io/gh/dvdl16/woocommerce_fusion/graph/badge.svg?token=A5OR5QIOUX)](https://codecov.io/gh/dvdl16/woocommerce_fusion)

WooCommerce connector for ERPNext v15

#### License

Dirk van der Laarse


#### User documentation

User documentation is hosted at [woocommerce-fusion-docs.finfoot.tech](https://woocommerce-fusion-docs.finfoot.tech)


#### Manual Installation

1. [Install bench](https://github.com/frappe/bench).
2. [Install ERPNext](https://github.com/frappe/erpnext#installation).
3. Once ERPNext is installed, add the woocommerce_fusion app to your bench by running

	```sh
	$ bench get-app https://github.com/dvdl16/woocommerce_fusion
	```
4. After that, you can install the woocommerce_fusion app on the required site by running
	```sh
	$ bench --site sitename install-app woocommerce_fusion
	```


#### Tests

To run unit and integration tests:

```shell
bench --site test_site run-tests --app woocommerce_fusion --coverage
```

##### InstaWP Requirement
For integration tests, we use InstaWP to spin up temporary Wordpress websites.

*TBD - steps to create a new site and template*

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
semgrep --config=/workspace/development/frappe-semgrep-rules/rules apps/woocommerce_fusion
```

If you use VS Code, you can specify the `.flake8` config file in your `settings.json` file:
```shell
"python.linting.flake8Args": ["--config=frappe-bench-v15/apps/woocommerce_fusion/.flake8_strict"]
```


The documentation has been generated using [mdBook](https://rust-lang.github.io/mdBook/guide/creating.html)

Make sure you have [mdbook](https://rust-lang.github.io/mdBook/guide/installation.html) installed/downloaded. To modify and test locally:
```shell
cd docs
mdbook serve --open
```
