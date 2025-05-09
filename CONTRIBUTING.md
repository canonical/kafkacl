# Contributing

## Overview

This documents explains the processes and practices recommended for contributing enhancements to
this library.

- Generally, before developing enhancements to this library, you should consider
  [opening an issue](https://github.com/canonical/kafkacl/issues) explaining
  your use case.
- If you would like to chat with us about your use-cases or proposed
  implementation, you can reach us at [Data Platform Matrix public channel](https://matrix.to/#/#charmhub-data-platform:ubuntu.com) or [Discourse](https://discourse.charmhub.io/).
- Familiarising yourself with the [Charmed Operator Framework](https://juju.is/docs/sdk) library will help you a lot when working
  on new features or bug fixes.
- All enhancements require review before being merged. Code review typically
  examines
  - code quality
  - test coverage
  - user experience.
- Please help us out in ensuring easy to review branches by rebasing your pull
  request branch onto the `main` branch. This also avoids merge commits and
  creates a linear Git commit history.

## Developing

Install `tox` and `poetry`

Install pipx: [https://pipx.pypa.io/stable/installation/](https://pipx.pypa.io/stable/installation/)

```shell
pipx install tox
pipx install poetry
```

You can create an environment for development:

```shell
poetry install
```

### Testing

```shell
tox run -e format        # update your code according to linting rules
tox run -e lint          # code style
tox run -e unit          # unit tests
tox run -e integration   # integration tests
```

## Canonical Contributor Agreement

Canonical welcomes contributions to the Kafka Connect Integrator Library.
check out our [contributor agreement](https://ubuntu.com/legal/contributors) if you're interested in contributing to the library.
