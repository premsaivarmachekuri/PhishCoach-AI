# Phishing Red-Flag Taxonomy and Explanations

## sender_mismatch
- **Tier:** 1
- **Title:** Sender Address Mismatch
- **Description:** The display name claims to be a trusted person, IT desk, or vendor, while the actual email domain does not match the organization or is misspelled (lookalike domain).
- **Guidance:** Always expand and inspect the full email address after the display name. Attackers often spoof display names while sending from unrelated or newly registered domains.

## urgency
- **Tier:** 1
- **Title:** Artificial Urgency or Threats
- **Description:** The message pressures you to act immediately—claiming account suspension, missed payroll, legal action, or an expiring deadline within minutes or hours.
- **Guidance:** Legitimate IT, HR, and finance teams rarely demand immediate credential entry or wire transfers without prior verification. Pause when a message creates panic.

## link_mismatch
- **Tier:** 1
- **Title:** Suspicious or Mismatched Link
- **Description:** The visible link text says one destination, but hovering reveals a different domain, an IP address, or an unexpected URL shortener.
- **Guidance:** Hover over links before clicking to preview the true destination domain. When in doubt, navigate directly to the known portal by typing its address or using a bookmark.

## credential_request
- **Tier:** 1
- **Title:** Unexpected Request for Credentials or MFA
- **Description:** The email asks you to sign in, reset a password, or approve a multi-factor authentication prompt you did not initiate.
- **Guidance:** Never enter passwords or approve MFA prompts from an unsolicited email link. Use your organization's official single sign-on portal directly.

## generic_greeting
- **Tier:** 2
- **Title:** Generic Greeting or Impersonal Tone
- **Description:** A sensitive internal or vendor notice addresses you as "Dear User", "Valued Employee", or omits context you would normally expect.
- **Guidance:** While not proof on its own, a generic greeting paired with an urgent action or link is a strong indicator of a mass-distributed phishing lure.

## authority_pressure
- **Tier:** 2
- **Title:** Executive or Authority Impersonation
- **Description:** The sender claims to be a senior leader, auditor, or legal counsel requesting confidential data, gift cards, or a fast payment bypass.
- **Guidance:** Verify any unusual request from leadership using a separate, trusted channel such as an internal directory phone number or verified chat handle.

## unusual_request
- **Tier:** 2
- **Title:** Unusual Business Process or Payment Change
- **Description:** Requests to bypass standard approval workflows, change vendor bank details, or share sensitive spreadsheets outside normal systems.
- **Guidance:** Follow established out-of-band verification procedures before altering payment details or sharing internal records.

## unexpected_attachment
- **Tier:** 2
- **Title:** Unexpected Attachment
- **Description:** An unrequested invoice, shipping notice, HR policy update, or archive file (`.zip`, `.html`, macro-enabled document) attached to prompt an immediate open.
- **Guidance:** Do not open unexpected attachments, especially HTML or archive files. Confirm with the purported sender via a known channel first.

## reward_lure
- **Tier:** 3
- **Title:** Reward, Bonus, or Refund Lure
- **Description:** Offers an unexpected bonus, tax refund, gift card, or prize that requires clicking a link and verifying account details to claim.
- **Guidance:** Treat unsolicited financial rewards or perks as suspicious and verify announcements on the official company intranet.
