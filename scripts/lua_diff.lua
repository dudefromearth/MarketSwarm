-- lua_diff.lua
-- Compare two JSON snapshots stored as Redis string keys
-- and store the resulting diff as a new key (third arg)

local cjson = require("cjson")

redis.log(redis.LOG_NOTICE, "[lua_diff] Starting diff computation")

-- Keys: [1] old snapshot key, [2] new snapshot key, [3] diff key
local old_key = KEYS[1]
local new_key = KEYS[2]
local diff_key = ARGV[1]

redis.log(redis.LOG_NOTICE, "[lua_diff] Keys: old=" .. tostring(old_key) .. ", new=" .. tostring(new_key) .. ", diff=" .. tostring(diff_key))

-- Fetch both JSON blobs
local old_json = redis.call("GET", old_key)
local new_json = redis.call("GET", new_key)

if not old_json or not new_json then
  redis.log(redis.LOG_WARNING, "[lua_diff] Missing one or both JSON inputs")
  return "Missing input snapshot"
end

local old_data = cjson.decode(old_json)
local new_data = cjson.decode(new_json)

local old_lookup = {}
for _, c in ipairs(old_data.contracts or {}) do
  old_lookup[c.ticker] = c
end

local diff = { added = {}, removed = {}, changed = {} }

for _, c in ipairs(new_data.contracts or {}) do
  local prev = old_lookup[c.ticker]
  if not prev then
    table.insert(diff.added, c)
  else
    if c.last_quote and prev.last_quote and c.last_quote.p and prev.last_quote.p and c.last_quote.p ~= prev.last_quote.p then
      table.insert(diff.changed, {ticker=c.ticker, old=prev.last_quote, new=c.last_quote})
    end
    old_lookup[c.ticker] = nil
  end
end

for t, c in pairs(old_lookup) do
  table.insert(diff.removed, c)
end

redis.call("SET", diff_key, cjson.encode(diff))
local summary = string.format("diff: +%d ~%d -%d", #diff.added, #diff.changed, #diff.removed)
redis.log(redis.LOG_NOTICE, "[lua_diff] Done — " .. summary)
return summary