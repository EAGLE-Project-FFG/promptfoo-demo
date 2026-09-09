# Evaluating KG construction with Promptfoo

This demo uses an LLM to turn application tables into a small knowledge graph. Promptfoo
evaluates the result in three ways: deterministic assertions, comparison
with a reference graph (ground truth), and an LLM judge. One test case is intentionally designed to fail, to see how Promptfoo reports an incorrect result.

Instructions to run the evaluation are described in Section 6.

## 1. Input

[data/demo_input.txt](data/demo_input.txt) is an excerpt from the existing data: two applications and their five components, stored in two CSV files.

The two tables join on **Application Service ID**, written `2` in one file and `2.0` in the
other. The model has to recognise that join and the numeric equivalence itself, the prompt
does not explain either. 

## 2. Expected Graph

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
IDs use `app:EAR-173` and `component:34` to keep the two kinds of identifier apart.

## 3. Prompt

[prompts/construct_kg.txt](prompts/construct_kg.txt) asks the model to construct a
knowledge graph using only facts supported by the data. It gives the JSON format and the
naming conventions, but no table-by-table extraction instructions and no join procedure.

The naming conventions are there because the evaluator compares IDs, types and relation
labels exactly. Without them an equivalent graph could fail purely because it chose
different labels. So this evaluates construction within a small agreed vocabulary, not a full ontology.

[promptfooconfig.yaml](promptfooconfig.yaml) runs the prompt with `gpt-5.4-mini`. The JSON
it returns is the constructed graph.

## 4. Assertions

Every assertion carries a `metric:` label, so the results table shows one column per group
of checks rather than a long list of pass/fail rows. The seven columns are `Format`,
`Content`, `NodeF1`, `EdgeF1`, `Faithfulness`, `Latency` and `Cost`.

### Deterministic Assertions

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

The two `javascript` assertions are one-line expressions written directly in the YAML.

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

### LLM-as-a-Judge

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

## 5. Test Cases

**1. Reference excerpt, correct reference.** The deterministic assertions and the reference
comparison on a graph that should come out right. Result: everything green, `NodeF1` and `EdgeF1`
at 1.00.

**2. Reference excerpt, reference with a typo.** The same excerpt as test case 1, compared
against
[data/demo_ground_truth_typo.json](data/demo_ground_truth_typo.json), which is a copy of the
reference in which one component name is misspelled `MSSQL BD` (instead of `DB`). This one is expected to
fail:

```
FAIL  NodeF1  score=0.86  TP=6 FP=1 FN=1 F1=0.86;
      missing=[('component:42', 'Component', 'MSSQL BD')];
      extra=[('component:42', 'Component', 'MSSQL DB')]
PASS  EdgeF1  score=1.00  TP=5 FP=0 FN=0 F1=1.00
```

It shows:

- The failure is localised. One metric goes red and names the exact tuple on each side. The
  other seven assertions in that test case stay green.
- `EdgeF1` is unaffected, because edges refer to node IDs and the typo is in a name.
- The model was right and the reference was wrong. An F1 comparison measures agreement with
  whatever reference you hand it, and a reference is hand-written data that can be wrong.

Test cases 1 and 2 send an identical request, so on an uncached run they are generated
separately and could in principle differ. In every run so far they came out identical.

**3. Unlabelled excerpt, spot checks and a judge.** A different excerpt,
[data/elvis_input.txt](data/elvis_input.txt) — application `EAR-168` and its four
components — with the two German free-text columns `Beschreibung` and `Description` kept
in. Nobody wrote a reference graph for it, which is the normal situation.

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

## 6. Running the Evaluation

Requirements: Node.js 24 and Python 3.

```bash
nvm use 24  # if you manage Node with nvm
export PROMPTFOO_PYTHON="$(command -v python3)"
export PROMPTFOO_CONFIG_DIR="$PWD/.promptfoo"
cp .env.example .env
```

Put your OpenAI key in `.env`:

```dotenv
OPENAI_API_KEY=your-openai-api-key
```

Then run the evaluation and open the results:

```bash
npx promptfoo@0.122.2 eval --env-file .env --no-cache -o results/kg.json
npx promptfoo@0.122.2 view
```

That runs the whole evaluation. Expect two rows green (success) and one red (fail), the red one being test case 2.

The run makes four model calls before any retries (three graph constructions and one
grading call for the judge) for well under a cent at `gpt-5.4-mini` prices. 

`--no-cache` is there on purpose. Promptfoo caches responses by default, and a cached run
replays old answers rather than evaluating anything: `Latency` and `Cost` then describe a
cache hit instead of a request, which makes those two columns pass trivially and mean
nothing. Drop the flag if you want cheap repeat runs and do not care about those two
columns.

Note that `promptfoo view` shows one evaluation at a time out of a local history in
`.promptfoo/`. Each `eval` run adds a new entry, and the UI opens the most recent.

### (Unit)Testing the Evaluator

The commands above evaluate the model. These two check our own evaluation code instead, so
they need no API key and take milliseconds:

```bash
python3 -m unittest -v test_graph_checks.py
npx promptfoo@0.122.2 validate config -c promptfooconfig.yaml
```

[graph_checks.py](graph_checks.py) is the only custom code here (everything else is a
Promptfoo built-in) and it is where a silent bug would do the most damage, because a wrong
F1 function still reports confident-looking numbers. [test_graph_checks.py](test_graph_checks.py)
feeds it hand-written graphs and checks that set comparison ignores ordering, that dropping
an edge gives 8/9 and adding one gives 10/11, that unusable output fails cleanly instead of
raising a stack trace in place of a score, and that test case 2 really does come out at
12/14 with `MSSQL BD` named in the reason.

`validate config` is smaller: a YAML and schema check that catches a misspelled assertion
type or bad indentation before you spend API calls on a run that could not have worked.

Neither says anything about whether the model builds good graphs or whether the rubric is a
good rubric. Only `eval` answers those.
