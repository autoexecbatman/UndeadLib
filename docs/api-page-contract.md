# API page - contract

**Spec of the spec.** This contract answers what the generated HTML page shows,
where each fact on it comes from, and what makes the build fail. It is the wrong
contract if the page can show a declaration the source does not have, omit one
it does, or pass while a public declaration is undocumented.

## Ownership

- **The source owns every fact on the page.** `docs/api_page.py` reads the
  headers with libclang and the Python binding with `ast`; `docs/api_page_js.py`
  reads the JavaScript binding line by line. Nothing is imported or executed, and
  no prose is written twice.
- **`docs/api_model.py` owns the data model** every reader produces and the
  renderer consumes.
- **The page is build output**: `build/docs/api.html`, self-contained (styles and
  script inlined), deterministic (no timestamp), never tracked.
- **Four sections**: the C API (`include/undead/undead.h`, parsed as C11), the
  C++ core (the other `include/undead/*.h`, parsed as C++20), the Python
  binding (`bindings/python/undead/__init__.py`), and the JavaScript binding
  (`bindings/js/undead.mjs`).

## What is listed

- **C and C++**: every namespace-level class, struct, enum, concept and function
  in the header itself, and the public constructors, methods and fields of each
  class. Private and protected members, forward declarations and friend
  declarations are not listed. Enum constants appear inside their enum, with their
  own comment where they have one. Macros are listed with the `/** */` block above
  them, except `UNDEAD_API`, which decorates declarations and is never used by a
  caller.
- **Python**: public module-level classes and functions, and each class's public
  methods plus `__init__`. Class-level constants appear inside their class.
- **JavaScript**: every exported `const`, `class` and `function`, and each
  exported class's constructor, methods (static ones included) and public fields.
  `#private` members and anything not exported are not listed. Any other
  `export` form (`export default`, `export { }`, `export let`) is refused with
  an error naming the line, so a new form cannot be skipped silently. Comments are
  JSDoc: `@param {type} name - text`, `@returns {type}`, `@throws {type}`,
  `@example`; any other tag is refused.
- **Each file's opening block** is its overview: for JavaScript, the `@file`
  block.
- **Signatures stop at the body**: a constructor's initializer list and a
  function's body are not interface.

## The coverage gate

`api_page.py --check` exits 1 naming each listed declaration with no comment,
and each file with no opening block. Enum constants and class constants are not
required, because their enclosing declaration documents them.

## Claims and checks

| Claim | Check |
|---|---|
| Every expected declaration is found, libclang's standard-library errors notwithstanding | Tests name each declaration in each header and module |
| Private members and forward declarations are absent | Tests name `UNREACHED`, `columnCount` and the forward `DialSearch` |
| JavaScript lists exports only, and refuses forms it does not know | Tests name `#wasm`, `requireSize`, `STATUS_NAMES`, and an `export default` |
| Signatures stop at the body | Tests on the constructor, a `const noexcept` method and the template |
| Doc tags render as sections | Unit tests on the comment parsers |
| The gate fails on an undocumented declaration | A test with a temporary header and module |
| The page's script is valid | `node --check` on the script file in the tests |
| The page looks right | A screenshot, read before it is called done |
