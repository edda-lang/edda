# router

A path router for HTTP handlers in Edda — register method-and-pattern routes
(with `:name` path parameters), then dispatch an incoming method and path to the
matching handler. Each route holds a `function(params: [Param]) -> String`
handler; matching extracts the captured parameters as a `[Param]` slice.

## Install

```
edda add router
```

Then import the modules you need:

```edda
import router.router
import router.route
```

## Usage

```edda
import router.router
import router.route

function greet(params: [route.Param]) -> String {
    return "hello"
}

function route_request(method: String, path: String, allocator: Allocator) -> String
    with {allocator, err: alloc.AllocError}
{
    var r = router.new(allocator)?
    router.get(mutable r, "/users/:id", greet, allocator)?
    return match router.dispatch(r, method, path, allocator)? {
        case .matched(let handler, let params) => handler(params)
        case .not_found                        => "404"
        case .method_not_allowed(let allowed)  => "405"
    }
}
```

`router.post` / `put` / `patch` / `delete` / `head` / `options` register a route
under their method; `router.add` takes an explicit method string. Inside a
handler, `route.param(params, name, allocator)` looks a captured parameter up by
name, returning a `Lookup` (`found` / `missing`).

## Public surface

- **`router.router`** — `new` builds an empty `Router`; `get` / `post` / `put` /
  `patch` / `delete` / `head` / `options` (and the explicit-method `add`)
  register routes; `dispatch` resolves a method and path to a `Dispatch`
  (`matched(handler, params)`, `not_found`, or `method_not_allowed(allowed)`).
- **`router.route`** — the `Param` type, `match_path` (test one pattern against a
  path, yielding a `MatchResult`), and `param` (look a captured parameter up by
  name, yielding a `Lookup`).
