# Automated releases

Release Please opens the version/changelog PR. After that PR is reviewed and
merged, the protected release job builds, tests, checks the distributions,
publishes through PyPI Trusted Publishing, and verifies the public version.

Configure `RELEASE_PLEASE_TOKEN`, required reviewers on the `sdk-production`
environment, and a PyPI Trusted Publisher for
`olusodotdev/oluso-py/.github/workflows/release.yml`. No PyPI password or API
token is stored. The shared contract job comes from `oluso-js`; merge its
contract workflow first.
