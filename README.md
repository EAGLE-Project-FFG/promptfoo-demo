# Evaluating KG construction with Promptfoo

An LLM builds a small knowledge graph from Swisscom application tables. Promptfoo runs the
construction and checks the result three ways: with deterministic assertions, by comparing
the graph against a reference graph, and with an LLM judge. One test case is deliberately
set up to fail, to show what a failure looks like.

Everything runs from a single command, described in section 6.

## 1. The input

[data/demo_input.txt](data/demo_input.txt) is an excerpt from the existing
[Swisscom data](../data/SwissCom/): two applications and their five components, taken from
two CSV files.

| Original source | Selected records | Selected columns |
| --- | --- | --- |
| [general.csv](../data/SwissCom/general.csv) | Application Service ID `2` and `3` | Application Service ID, Application ID, Application Name |
| [komponenten.csv](../data/SwissCom/komponenten.csv) | Application Service ID `2.0` and `3.0` | Application Service ID, Component ID, Name |

The excerpt preserves these field values. Other records and columns are left out to keep
the example small. No source CSV was modified and no facts were added.

The two tables join on **Application Service ID**, written `2` in one file and `2.0` in the
other. The model has to recognise that join and the numeric equivalence itself; the prompt
does not explain either. This service key is not the same as the application's `EAR-...`
identifier.

## 2. The expected graph

[data/demo_ground_truth.json](data/demo_ground_truth.json) is the reference for that
excerpt: seven nodes and five edges.

```text
B2B Gateway Infrastruktur (EAR-173)
  --has_component--> IBM Datapower (34)

Chromeleon (EAR-172)
  --has_component--> Management PC (39)
  --has_component--> Desktop Client (40)
  --has_component--> Notebook Client (41)
  --has_component--> MSSQL DB (42)
```

Nodes carry an ID, a type (`Application` or `Component`), and the exact name from the CSV.
IDs use `app:EAR-173` and `component:34` to keep the two kinds of identifier apart. Only
component membership is represented; component subtypes and other properties are out of
scope here.

The reference was written from the selected source records for this demo. It is not a
pre-existing full Swisscom reference graph. It stays out of the prompt and is read only by
the evaluator.

## 3. The prompt

[prompts/construct_kg.txt](prompts/construct_kg.txt) asks the model to construct a
knowledge graph using only facts supported by the data. It gives the JSON format and the
naming conventions, but no table-by-table extraction instructions and no join procedure.

The naming conventions are there because the evaluator compares IDs, types and relation
labels exactly. Without them an equivalent graph could fail purely because it chose
different labels. So this evaluates construction within a small agreed vocabulary, not the
free choice of an ontology.

[promptfooconfig.yaml](promptfooconfig.yaml) runs the prompt with `gpt-5.4-mini`. The JSON
it returns is the constructed graph. There is no graph database to set up.

## 4. The checks

Every assertion carries a `metric:` label, so the results table shows one column per group
of checks rather than a long list of pass/fail rows. The seven columns are `Format`,
`Content`, `NodeF1`, `EdgeF1`, `Faithfulness`, `Latency` and `Cost`.

### Deterministic assertions

Promptfoo's built-in checks. They need no reference graph and no second model call, they
cost nothing, and they give the same answer every run.

| Assertion | Where | What it checks |
| --- | --- | --- |
| `is-json` | every test | the output parses as JSON |
| `not-contains: "```"` | every test | the model returned bare JSON, not a fenced code block |
| `contains: has_component` | every test | the agreed relation label is present |
| `javascript` | every test | every node ID matches `^(app\|component):.+` |
| `contains-all` | tests 1 and 3 | each expected name and ID appears verbatim in the output |
| `javascript` | test 1 | the graph has exactly 7 nodes and 5 edges |
| `not-contains-any` | test 3 | `Medango`, `PrintingService` and `Printing Service` do not appear |
| `latency`, `cost` | every test | the request stayed under 60 s and $0.05 |

The two `javascript` assertions are one-line expressions written directly in the YAML; the
JSON parsing and the regex are done by Promptfoo, not by us.

### Comparison against the reference graph

[graph_checks.py](graph_checks.py) holds two functions of about ten lines each, wired in as
`type: python` assertions. `check_nodes` compares the set of `(id, type, name)` tuples and
`check_edges` the set of `(source, relation, target)` triples. Both report correct items
(TP), extra items (FP), missing items (FN) and `F1 = 2 TP / (2 TP + FP + FN)`, and pass
only when the two sets match exactly. Ordering does not matter.

Each assertion names its reference file in its own `config:` block, which Promptfoo passes
through to the Python function:

```yaml
- type: python
  value: file://graph_checks.py:check_nodes
  metric: NodeF1
  config:
    reference: data/demo_ground_truth.json
```

That is what lets the same two functions be pointed at a different reference, which the
next section uses.

### The LLM judge

The deterministic assertions check form and a handful of strings we listed by hand. The
reference comparison checks content exactly, but only for an excerpt someone has labelled.
Test case 3 has no reference graph, which is the normal situation for this data, so it
carries one model-graded assertion instead:

```yaml
- type: llm-rubric
  metric: Faithfulness
  threshold: 0.8
  value: |
    Every node in the graph must correspond to a record in the tables below.

    {{data}}

    The Beschreibung and Description columns are prose about the records, not
    records of their own. Fail if a node comes from that prose instead of from a
    record, and name it. Otherwise pass.
```

The rubric interpolates `{{data}}`, so the judge sees the same tables the model saw and
needs no reference graph of its own. It states one criterion, and that is the difference
from the `not-contains-any` blocklist beside it: the blocklist catches the three inventions
we could name in advance, the judge applies the criterion to whatever the model returns.
Checked against hand-written graphs, it passed a faithful one and rejected both an added
`Oracle DB` node and an added `Medango` application, naming each. `Oracle DB` is the
interesting one, because catching it means knowing that `Oracle 19` in the description of
`Elvis DB` and a node called `Oracle DB` are the same thing.

Three details worth knowing:

- The judge model is set under `defaultTest.options.provider`, separately from the provider
  that builds the graph.
- `threshold: 0.8` is not decoration. Promptfoo takes pass/fail from the grader's `pass`
  field and assumes `true` when the field is missing, so a rubric that scores 0.0 on a
  failure would otherwise still pass.
- The rubric has to stay inline. Promptfoo does not run Nunjucks over a rubric loaded with
  `value: file://...`, so `{{data}}` would arrive as literal text and the judge would grade
  the graph without ever seeing the tables, then invent plausible reasons.

This is the one check here whose verdict is not reproducible run to run.

## 5. The three test cases

**1. Reference excerpt, correct reference.** The deterministic assertions and the reference
comparison on a graph that should come out right. Everything green, `NodeF1` and `EdgeF1`
at 1.00.

**2. Reference excerpt, reference with a typo.** The same excerpt as test case 1, compared
against
[data/demo_ground_truth_typo.json](data/demo_ground_truth_typo.json) — a copy of the
reference in which one component name is misspelled `MSSQL BD`. This one is expected to
fail:

```
FAIL  NodeF1  score=0.86  TP=6 FP=1 FN=1 F1=0.86;
      missing=[('component:42', 'Component', 'MSSQL BD')];
      extra=[('component:42', 'Component', 'MSSQL DB')]
PASS  EdgeF1  score=1.00  TP=5 FP=0 FN=0 F1=1.00
```

What it shows is worth more than the failure itself:

- The failure is localised. One metric goes red and names the exact tuple on each side; the
  other seven assertions in that test case stay green.
- `EdgeF1` is unaffected, because edges refer to node IDs and the typo is in a name.
- The model was right and the reference was wrong. An F1 comparison measures agreement with
  whatever reference you hand it, and a reference is hand-written data that can be wrong.

Test cases 1 and 2 send an identical request, so on an uncached run they are generated
separately and could in principle differ. In every run so far they came out identical.

**3. Unlabelled excerpt, spot checks and a judge.** A different excerpt,
[data/elvis_input.txt](data/elvis_input.txt) — application `EAR-168` and its four
components — with the two German free-text columns `Beschreibung` and `Description` kept
in. Nobody wrote a reference graph for it, which is the normal situation: there are 69
applications in [general.csv](../data/SwissCom/general.csv) and no reference graph for any
of them.

Those columns are where the interesting failures live, because they talk *about* records
without *being* records:

- `Beschreibung` mentions `Weblogic` and `Oracle DB`. Both are already component records
  (`47` and `45`), so a graph that adds separate nodes for them describes the same thing
  twice.
- It also mentions `Medango`, an application with no record in this excerpt.
- A `Description` mentions `PrintingService`, which has no Component ID.
- The `Type` column says `Application` for component `35` and `Middleware` for `47`. In our
  vocabulary all four rows are `Component`.

With no reference to compare against, the deterministic checks can only be spot checks:
`contains-all` for the five names that must appear, and `not-contains-any` as a blocklist of
the three inventions we can name in advance. The judge covers what a blocklist cannot.

## 6. Running it

Node.js 24 and Python 3. No Python packages needed.

```bash
cd Promptfoo_minimal
nvm use 24  # if you manage Node with nvm
export PROMPTFOO_PYTHON="$(command -v python3)"
export PROMPTFOO_CONFIG_DIR="$PWD/.promptfoo"
```

Put your OpenAI key in `.env` (keep the existing file if it is already set up):

```dotenv
OPENAI_API_KEY=your-openai-api-key
```

Then run the evaluation and open the results:

```bash
npx promptfoo@0.122.2 eval --env-file .env --no-cache -o results/kg.json
npx promptfoo@0.122.2 view
```

That is the whole evaluation: one command, one results table, three rows. Expect two rows
green and one red, the red one being test case 2.

The run makes four model calls before any retries — three graph constructions and one
grading call for the judge — for well under a cent at `gpt-5.4-mini` prices. A failed
assertion is an evaluation result; an authentication or API error means the call did not
complete.

`--no-cache` is there on purpose. Promptfoo caches responses by default, and a cached run
replays old answers rather than evaluating anything: `Latency` and `Cost` then describe a
cache hit instead of a request, which makes those two columns pass trivially and mean
nothing. Drop the flag if you want cheap repeat runs and do not care about those two
columns.

Note that `promptfoo view` shows one evaluation at a time out of a local history in
`.promptfoo/`. Each `eval` run adds a new entry, and the UI opens the most recent; there is
a selector for the older ones.

### Testing the evaluator

The commands above evaluate the model. These two check our own evaluation code instead, so
they need no API key and take milliseconds:

```bash
python3 -m unittest -v test_graph_checks.py
npx promptfoo@0.122.2 validate config -c promptfooconfig.yaml
```

[graph_checks.py](graph_checks.py) is the only custom code here — everything else is a
Promptfoo built-in — and it is where a silent bug would do the most damage, because a wrong
F1 function still reports confident-looking numbers. [test_graph_checks.py](test_graph_checks.py)
feeds it hand-written graphs and checks that set comparison ignores ordering, that dropping
an edge gives 8/9 and adding one gives 10/11, that unusable output fails cleanly instead of
raising a stack trace in place of a score, and that test case 2 really does come out at
12/14 with `MSSQL BD` named in the reason.

`validate config` is smaller: a YAML and schema check that catches a misspelled assertion
type or bad indentation before you spend API calls on a run that could not have worked.

Neither says anything about whether the model builds good graphs or whether the rubric is a
good rubric. Only `eval` answers those.

## 7. Scope

This covers the KG construction step on one small excerpt with a hand-written reference
graph. It is not a benchmark of extraction quality, and numbers from seven nodes do not
generalise. More excerpts can be added as further test cases.

The three kinds of check cover different ground, which is why all three are here.
Deterministic assertions are free and reproducible, but only check form and strings we
listed by hand. The reference comparison is exact, but needs an excerpt someone has
labelled. The judge needs no labels and is therefore the only one of the three that could
be pointed at all 69 applications, but its verdict varies between runs and its rubric here
states a single criterion rather than a full specification of a correct graph.

An earlier version of this directory held a schema-extraction experiment with a LiteLLM
provider, generated scenarios and heuristic entity checks. That has been removed. This
evaluation is the only one here, and there is no scenario-generation step.
