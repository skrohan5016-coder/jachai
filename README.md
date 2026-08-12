# jachai

**Find the inputs that break generated code.**

Writing code is cheap now. Trusting it is not. `jachai` reads a Python file,
works out what its functions implicitly promise, then actively tries to break
those promises — and reports only the breaks that look like real defects.

No dependencies. No API keys. No language model in the loop.

```
$ jachai check payments.py

payments.py
  line 13   average(values)
    !  ZeroDivisionError on values=empty list
       division by zero — this exception type is almost never raised on
       purpose, so the input path looks unhandled.

  line 19   normalise_tags(tags)
    !  modifies its argument 'tags' and also returns a value
       The caller's object is changed in place while the function looks pure
       from the outside. Copy the argument before modifying it, or return None.

  line 26   find_user(users, name)
    !  declared -> dict but returned None on typical values  (+9 more inputs)
       A code path falls off the end of the function without returning.

  line 51   add(a, b)
    ok  nothing broke across 9 inputs

  9 functions checked · 84 calls · 6 likely bugs, 0 worth a look · 2.01s
```

## Install

```bash
pip install jachai        # once published
pip install -e .          # from a clone
```

Python 3.10+. The standard library is the only requirement, on purpose: a
checker you have to fight to install is a checker you stop running.

## Use

```bash
jachai check src/module.py             # one file
jachai check src/*.py --quiet          # only show problems
jachai check src/ --json               # machine readable
jachai check src/ --fail-on any        # stricter CI gate
```

Exit codes: `0` clean, `1` findings, `2` the file could not be read or imported.

In GitHub Actions:

```yaml
- run: pip install jachai
- run: jachai check src/ --quiet
```

## What it checks

| Check | Catches |
|---|---|
| **crash** | Unhandled exceptions on empty, zero, negative, huge, or non-ASCII input |
| **hang** | Calls that never return — unbounded loops, runaway recursion |
| **mutation** | Functions that quietly modify a caller's list or dict while looking pure |
| **contract** | A declared return type the function does not actually honour |
| **shared-default** | `def f(items=[])` — one object shared by every call, forever |
| **determinism** | Same input, different answer, with no clock or random source in sight |

## The one design rule

> **A model may guess. Only a program may conclude.**

Nothing in a `jachai` report was asserted by a language model. Every finding was
observed by actually running your function and watching what happened. Asking a
model whether code is correct just adds a second thing you cannot verify; the
whole point is to remove one.

Future versions may use a model to *propose* properties worth testing. The
verdict will always come from execution.

## Why the reports are short

The failure mode for tools like this is not missing bugs. It is crying wolf.
A checker that reports fifty things, forty of which are fine, gets muted within
a week — and then it catches nothing at all.

So `jachai` stays quiet when it is not sure. It says nothing when:

- the function validates its own input and the exception it raised is one it
  raises on purpose;
- an argument's type could not be inferred, so any value we passed was our guess
  and any resulting `TypeError` is our fault;
- an argument is annotated with a class we cannot construct — including
  `list[YourClass]`, where filling the list with integers would be just as wrong;
- the module imports `random` or `time`, so varying results are expected;
- a returned object has no meaningful equality, so "different" cannot be judged;
- the signature is `*args, **kwargs`, which tells us nothing about a valid call.

Every one of those rules exists because the tool once reported a false positive
against its own source code. Each has a regression test in
`tests/test_jachai.py::TestDogfoodRegressions`.

## Honest limitations

- **It imports your file, so your module-level code runs.** Do not point it at
  code that charges credit cards on import. Run it on the same code you would
  run a test suite against.
- Module-level functions only. Methods, nested functions and `async def` are not
  covered yet.
- Functions taking your own classes are skipped rather than guessed at.
- It finds *contradictions*, not incorrect business logic. A function that
  confidently computes the wrong tax rate looks perfectly healthy here.
- Passing `jachai` is not proof of correctness. It is proof that a specific,
  narrow set of promises was not visibly broken.

## Prior art worth your time

`jachai` occupies a small gap between much larger tools, and is not a
replacement for any of them:

- [Hypothesis](https://hypothesis.works/) — property-based testing done
  properly. If you can write your own properties, write them there.
- [CrossHair](https://crosshair.readthedocs.io/) — symbolic execution against
  contracts, and far deeper than this.
- [Daikon](https://plse.cs.washington.edu/daikon/) — the original work on
  inferring invariants from execution.
- [mutmut](https://mutmut.readthedocs.io/) — mutation testing: are your tests
  worth anything?

What those need and `jachai` does not is for you to already know what to assert.
This runs on a file you were handed thirty seconds ago.

## Development

```bash
python -m unittest discover -s tests -v   # 56 tests, no dependencies
python -m jachai check jachai/*.py        # the tool, on itself
```

The second command is not a formality. Every false positive listed above was
found that way.

## Licence

MIT.
