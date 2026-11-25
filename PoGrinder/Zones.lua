local _, ns = ...
-- Étape 3 : estimation de l'or/heure par zone, à partir de ZoneDB (généré par tools/gen.py)
-- et des prix TSM en direct, corrigée par l'or/h mesuré dans le journal de loot.

local Zones = {}
ns.Zones = Zones

local defaults = {
  killsPerHour = 90,   -- kills par heure en farm continu
  nodesPerHour = 60,   -- nœuds récoltés par heure dans une zone dense
  denseNodes = 150,    -- en dessous, la zone est jugée moins dense (nœuds/h réduits)
  priorSecs = 1800,    -- poids de l'estimation face à la mesure (en secondes de jeu)
  minMeasured = 600,   -- temps mesuré minimum avant de corriger l'estimation
}
local function cfg(k)
  local v = ns.db and ns.db[k]
  if v == nil then v = defaults[k] end
  return v
end
Zones.defaults = defaults

-- Métiers de récolte du joueur (nil si impossible à détecter : on garde tout)
local function gatheringSkills()
  local has, found = {}, false
  if GetProfessions and GetProfessionInfo then
    for _, idx in ipairs({ GetProfessions() }) do
      if idx then
        local _, _, _, _, _, _, line = GetProfessionInfo(idx)
        if line == 186 then has.m = true end
        if line == 182 then has.h = true end
        found = true
      end
    end
  end
  if not found and GetNumSkillLines and GetSkillLineInfo then
    for i = 1, GetNumSkillLines() do
      local name = GetSkillLineInfo(i)
      if name == "Minage" or name == "Mining" then has.m = true; found = true end
      if name == "Herboristerie" or name == "Herbalism" then has.h = true; found = true end
    end
  end
  return found and has or nil
end

local function makePricer()
  local cache = {}
  return function(itemID)
    local v = cache[itemID]
    if v == nil then
      local ok, p = pcall(ns.Prices.Get, itemID)
      v = ok and p and p.best or 0
      cache[itemID] = v
    end
    return v
  end
end

-- Or/h mesuré par zone (agrège les cartes du journal vers les zones)
local function measured()
  local out = {}
  local log = PoGrinderLog
  if not (log and log.zones and ns.UiToArea) then return out end
  for map, z in pairs(log.zones) do
    local area = ns.UiToArea[map]
    if area then
      local m = out[area] or { secs = 0, value = 0 }
      out[area] = m
      m.secs, m.value = m.secs + (z.secs or 0), m.value + (z.value or 0)
    end
  end
  return out
end

local function scoreZone(area, z, level, skills, price)
  local r = { area = area, gather = 0, mobs = 0, top = nil, topVal = 0 }
  local contrib = {}

  -- Récolte
  local total, nodes = 0, 0
  for _, n in ipairs(z.n or {}) do
    local kind, count, list = n[1], n[2], n[3]
    if not skills or skills[kind] then
      local v = 0
      for i = 1, #list, 2 do
        local iv = list[i + 1] * price(list[i])
        v = v + iv
        contrib[list[i]] = (contrib[list[i]] or 0) + iv * count -- mis à l'échelle /h plus bas
      end
      total, nodes = total + v * count, nodes + count
    end
  end
  if nodes > 0 then
    local nph = cfg("nodesPerHour") * math.min(1, nodes / cfg("denseNodes"))
    r.gather = total / nodes * nph
    r.nodes = nodes
    for id, v in pairs(contrib) do contrib[id] = v / nodes * nph end
  end

  -- Mobs : meilleure tranche de niveau accessible
  for _, m in ipairs(z.m or {}) do
    local lo, hi = m[1], m[2]
    if hi >= level - 5 and lo <= level + 2 then
      local perKill = math.max(0, m[4]) + math.max(0, m[5])
      local drops = m[6]
      for i = 1, #drops, 2 do perKill = perKill + drops[i + 1] * price(drops[i]) end
      local gph = perKill * cfg("killsPerHour")
      if gph > r.mobs then
        r.mobs, r.lo, r.hi, r.goldOnly = gph, lo, hi, m[4] < 0
        r.drops = drops
      end
    end
  end
  for i = 1, #(r.drops or {}), 2 do
    local id = r.drops[i]
    contrib[id] = (contrib[id] or 0) + r.drops[i + 1] * price(id) * cfg("killsPerHour")
  end

  r.estimate = math.max(r.gather, r.mobs + 0.5 * r.gather)
  for id, v in pairs(contrib) do
    if v > r.topVal then r.top, r.topVal = id, v end
  end
  return r
end

function Zones.Rank(level)
  level = level or UnitLevel("player") or 60
  local skills = gatheringSkills()
  local price = makePricer()
  local meas = measured()
  local rows = {}
  for area, z in pairs(ns.ZoneDB or {}) do
    local r = scoreZone(area, z, level, skills, price)
    r.final = r.estimate
    local m = meas[area]
    if m and m.secs >= cfg("minMeasured") then
      r.measured = m.value / m.secs * 3600
      r.measuredMin = m.secs / 60
      local w = cfg("priorSecs")
      r.final = (r.measured * m.secs + r.estimate * w) / (m.secs + w)
    end
    if r.final > 0 then rows[#rows + 1] = r end
  end
  table.sort(rows, function(a, b) return a.final > b.final end)
  return rows, skills, level
end

function Zones.Report(n)
  n = n or 8
  local rows, skills, level = Zones.Rank()
  local metiers = not skills and "métiers non détectés, récolte comptée"
    or ((skills.m and "minage " or "") .. (skills.h and "herboristerie" or ""))
  if metiers == "" then metiers = "aucun métier de récolte" end
  ns.Print(string.format("Meilleures zones pour un niveau %d (%s) :", level, metiers))
  for i = 1, math.min(n, #rows) do
    local r = rows[i]
    local parts = {}
    if r.gather > 0 then parts[#parts + 1] = "récolte " .. ns.Money(r.gather) .. "/h" end
    if r.mobs > 0 then
      parts[#parts + 1] = string.format("mobs %s/h (niv %d-%d)", ns.Money(r.mobs), r.lo, r.hi)
    end
    local line = string.format("%d. %s : ~%s/h", i, ns.ZoneName(r.area), ns.Money(r.final))
    if r.measured then
      line = line .. string.format(" |cff33ff99(mesuré %s/h sur %d min)|r", ns.Money(r.measured), r.measuredMin)
    end
    ns.Print(line)
    local detail = table.concat(parts, ", ")
    if r.top then detail = detail .. " ; surtout : " .. ns.ItemName(r.top) end
    ns.Print("     |cffaaaaaa" .. detail .. "|r")
  end
  if #rows == 0 then ns.Print("Aucune zone exploitable trouvée.") end
end
