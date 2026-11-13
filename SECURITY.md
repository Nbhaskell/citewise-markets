# Security policy

Citewise for Markets is a prototype research tool. It runs on one PC, with a local model and its own Postgres database, and is not offered as a hosted service. It stores real public market data (SEC filings, daily prices and headline titles) that it downloads itself; the repository contains no price, headline or filing dataset. It has no login, so the API listens on `127.0.0.1` and must not be exposed to a network (see the README). Its answers are not financial advice.

## Reporting a vulnerability

Report a suspected vulnerability privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Do not open a public issue for it.

Please include what you found, how to reproduce it, and what it lets someone do. Reports are read and answered as time allows; there is no bug bounty.

## In scope

- Secrets or personal data committed to the repository or its history. `.env` is private; secret scanning with push protection and a gitleaks scan of the whole history in CI are on.
- Anything that makes the API reachable from outside the local machine, or that lets a web page from another origin call it (the API binds to `127.0.0.1` and accepts only the local web app's origin).
- Anything that lets the API change data beyond its two documented writes (adding and removing a tracked company).
- Model or API text rendered as HTML in the web app (it is rendered as text only).
- A way to make the copilot give a buy, sell or hold recommendation without the fixed advice notice, or to use earlier turns of a chat as evidence for an answer (both are guarded in code and by tests).
- A vulnerable dependency that is reachable in this project's use of it.

Known limits (answers from a small local model can be wrong, unlicensed price and headline sources, no login) are listed in the README; a new example of a listed limit is still welcome.
