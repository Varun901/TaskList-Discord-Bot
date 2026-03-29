# Privacy Policy

**Last updated: March 29, 2026**

This Privacy Policy explains what data **TaskList Bot** ("the Bot", "we", "us") collects, how it is used, and what rights you have over your data. By using the Bot you agree to the practices described here.

---

## 1. What Data We Collect

When you use the Bot, the following data is stored in a local SQLite database on the server where the Bot is hosted:

### 1.1 Account & Configuration Data
| Field | Purpose |
|---|---|
| Discord User ID | Uniquely identifies your account across commands |
| Discord Guild (Server) ID | Associates your configuration with a specific server |
| Calendar Source | `google` or `notion` — your chosen integration type |
| Calendar / Database ID | Your Google Calendar ID or Notion Database ID |
| Digest Channel ID | The Discord channel where your daily digest is posted |
| Notion Integration Token | Required only for Notion users; stored to authenticate API calls |

### 1.2 Task Data
- **Manual tasks** you create via `/add`: task name, optional description, optional due date, and completion status.
- **Completed task records**: the name and source (`calendar` or `manual`) of tasks you mark complete, along with the timestamp of completion.
- **Reminders**: task name, scheduled reminder datetime, fired/snoozed state.
- **Daily reminder schedule**: the hour and minute you configured for your end-of-day check-in, and whether it is enabled.

### 1.3 Data We Do NOT Collect
- We do not store the full contents of your Google Calendar or Notion database. Calendar and Notion data is fetched **in real time** on demand and is not persisted beyond the duration of the request.
- We do not collect your IP address, browser information, or any data outside of Discord interactions.
- We do not use cookies or tracking pixels.

---

## 2. How We Use Your Data

Your data is used exclusively to operate the Bot's features:

- **Delivering your daily task digest** and end-of-day check-in to your configured channel.
- **Firing reminders** at the time you specified.
- **Tracking task completion** to power streaks and weekly summary statistics shown in `/weekly` and `/status`.
- **Displaying your tasks** in response to `/tasks`, `/mytasks`, and related commands.
- **Showing aggregated, non-identifying pending counts** when another user runs `/nudge` on you (task *names* are never exposed to the nudging user).

We do not use your data for advertising, analytics sold to third parties, or any purpose outside of providing the Bot's functionality.

---

## 3. Third-Party Services

When you run commands that require fetching calendar data, the Bot makes outbound requests to:

- **Google Calendar API** (public iCal endpoint) — governed by [Google's Privacy Policy](https://policies.google.com/privacy).
- **Notion API** — governed by [Notion's Privacy Policy](https://www.notion.so/Terms-and-Privacy-28ffdd083dc3473e9c2da6ec011b58ac).

The Bot acts as a relay; it does not store the content fetched from these services beyond the lifetime of a single request. Your use of these third-party services is subject to their own privacy policies.

---

## 4. Data Storage and Security

- All data is stored in a **SQLite database** on the host machine running the Bot.
- Notion integration tokens are stored as plaintext in the database. You should use a Notion integration with the **minimum necessary permissions** (read-only access to the relevant database) and revoke it at any time from your [Notion integrations page](https://www.notion.so/my-integrations) if you no longer use the Bot.
- The developer takes reasonable precautions to secure the host environment, but no system is perfectly secure. Use the Bot at your own discretion.

---

## 5. Data Retention

Your data is retained for as long as you use the Bot. You can permanently delete **all** data associated with your Discord account at any time by running:

```
/unlink
```

This command immediately removes your configuration, manual tasks, completed-task history, reminders, and daily-reminder schedule from the database. Data deleted this way cannot be recovered.

---

## 6. Your Rights

You have the right to:

- **Access** your data by using `/status`, `/mytasks`, `/reminders`, and `/weekly`.
- **Delete** all your data at any time via `/unlink`.
- **Correct** your configuration at any time by running `/setup` again.

If you have questions or concerns about your data that cannot be addressed through the Bot's commands, contact us at the address in Section 9.

---

## 7. Children's Privacy

The Bot is not directed at children under the age of 13. Discord itself requires users to be at least 13 years old. We do not knowingly collect data from anyone under 13. If you believe a user under 13 has used the Bot, please contact us and we will delete their data promptly.

---

## 8. Changes to This Policy

We may update this Privacy Policy from time to time. The "Last updated" date at the top of this page reflects the most recent revision. Your continued use of the Bot after changes are posted constitutes acceptance of the revised policy. Significant changes will be announced where reasonably practicable.

---

## 9. Contact

If you have any questions or requests regarding this Privacy Policy, please contact: **[CONTACT EMAIL]**
