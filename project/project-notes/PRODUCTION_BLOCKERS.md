# Production blockers — must be resolved before publication

This checklist intentionally distinguishes repository work from facts that only the site owner, the bar association, and the selected hosting provider can confirm.

## Professional details

- [ ] Confirm the exact public name of the attorney formation and the official address or other location details required by the Moscow Region Bar Association.
- [ ] Obtain and retain the Bar Association's position on the address format to be published. Do not substitute a residential address without an explicit decision.
- [ ] Verify the attorney's current registry entry, registration number, status, education and other biographical claims against authoritative records.
- [ ] Confirm permission and consent for publication of the portrait and all third-party materials.
- [ ] Confirm the fee schedule and every displayed amount in writing with the site owner.

## Personal data and hosting

- [ ] Identify the personal-data operator and document the actual purposes, categories, legal bases, recipients and retention periods.
- [ ] Select the hosting provider and confirm where website files, access logs, backups and support tickets are stored and processed.
- [ ] Obtain the provider's current data-processing terms and list of subprocessors.
- [ ] Determine whether Roskomnadzor notification is required and complete it before processing where required.
- [ ] Draft and publish a privacy notice only after the real data flows and hosting arrangements are known. Do not publish a generic template that claims unverified facts.
- [ ] Define log retention and deletion with the provider; verify backup location, encryption, access control and restore procedure.
- [ ] Enable MFA for registrar, DNS, hosting, Git and email; review mailbox sessions, forwarding rules, recovery methods and connected apps.

## Production infrastructure

- [ ] Configure the real domain, DNS, TLS renewal, HTTP-to-HTTPS redirect and security headers.
- [ ] Verify CSP against the actual deployed pages; do not weaken it to make third-party embeds work.
- [ ] Confirm the web root contains only the generated public build, not source files, Git metadata, configuration, secrets or backups.
- [ ] Run the post-deployment checklist in `project/deploy/DEPLOY.md` from Russian fixed and mobile networks.
- [ ] Test restore and rollback before announcing the site.

## Editorial review

- [ ] Verify every court citation against the full primary judicial act and its procedural history.
- [ ] Keep the consumer-penalty article excluded from indexing until its cited acts and conclusions have been checked.
- [ ] For each article, retain publication date, last legal review date and primary-source references. Do not invent review dates.
