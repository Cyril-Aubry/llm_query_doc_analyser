
---

# 📝 Project Development Checklist

## 1. Define the idea

* **What problem am I solving?**
  1. **V1:** Having a list of scientific papers retrieved by a scientific database search engine query, I want to filter the most relevant for my goal and try to download the full text pdf.
  2. **V2:** If the paper's reference is a pre-print from arXiv for example, try to find the published paper as well.
* **Who is it for?**
  For me
* **What is the goal?**
   1. **V1:** import excel/CSV file, store and manage paper's references, filter the list for most relevant and download pdf with adequate filename or get url for manual download.
  2. **V2:** Manage pre-print and their possible published version.
* **What am I not doing now?**
  Don't manage the updating process of already enriched, resolved or downloaded records. Don't manage the fact of importing same record of research article later on with updated citations number and other data to be updated (check if import date is out of date for example).

---

## 2. Break into small steps

### V1
1. Identify a unique paper by a surrogate PK and assign a unique constraint on its DOI, with an import datetime.
2. Implement a unique constraint error management for user to be notified if paper already imported
3. Timestamp each command/actions to inform on import, enrich, resolve and download actions for each processed records
4. Prevent redoing actions on already processed records

### V2
1. Clarify what to do with pre-print version and possible published version of the pre-print

---

## 3. Define “done” for each step

### V1

* **Step 1:** Unique paper ID with doi unique constraints with import datetime
  * Expected: Apply unique constraints on DOI in the table records and add import datetime
  * Check: try to import the same doi paper and check for database constraint error and no duplicate entry.

* **Step 2:** unique constraints error management
  * Expected: When same doi paper importation, notify and log error on constraints
  * Check: try to import the same doi paper and check for adequate notification

* **Step 3:** add timestamp for each action records: Import, enrich, filter(done on filtering query -> rename), resolve (done -> rename) and download (done -> rename)
  * Expected: Apply unique constraints on DOI in the table records and add import datetime
  * Check: check timestamp adequate timing on actions trigger

* **Step 4:** no duplication of actions on processed records
  * Expected: Exclude running import, enrich, resolve and download on already processed records.
  * Check: try command with already processed records and check timestamp remain previous and no processing done on those records.


### V2

* **Step 2:** pre-print version vs published version
  * Expected: If a record was imported as a pre-print version (arXiv), it should be distinguishable from an actual published paper, and if a pre-print as a published version it should be distinguishable.
  * Check: run each actions, and check that the enrichment datetime, resolve datetime and download datetime is not updated for new action run on previous records



---

## 4. Set up a simple home for the project

Make a folder like this:

```
my_project/
├─ app/        # your code
│  └─ main.py  # the entry point (start here)
├─ tests/      # simple checks or experiments
├─ README.md   # what it does + how to run
```

👉 Just enough to stay tidy.

---

## 5. Build the smallest slice first

Ask: *What’s the smallest thing I can build that shows the idea works?*

* Do **only that** before adding more features.
* Show/test it, then improve.

---

## 6. Work in short cycles

Repeat this loop:

1. Pick one step.
2. Build it.
3. Test/check it.
4. Update your notes (README).
5. Show/demo if possible.

---

## 7. Keep track of progress

### Version 1
- [v] Rename records table to research_articles in the whole project
- [V] Clean-up records database fields, deleting unused and moving some to the adequate tables
- [V] Add a unique constraint on the DOI field of the research_articles table
- [V] Implemented IntegrityError catch and notification of skipped import for user
- [V] Added an import_datetime and enrichment datetime for each record importation and enrichment
- [V] Excluded enrichment of records having a enrichment_datetime value
- [V] Refactors filtering query timestamp handling. Renames filtering query timestamp fields to clarify their meaning and removes redundant timestamp storage from filter results.
- []

---

✅ At the end, you’ll always have:

* A **clear goal**,
* A **small working version**,
* A **path forward** without being overwhelmed.

---

