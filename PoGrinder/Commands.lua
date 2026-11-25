local _, ns = ...

local TOP = 15

local function fmtRate(r)
  return r and string.format("%.1f%%", r * 100) or "-"
end

local function priceLine(itemID, p)
  return string.format("%s  HV:%s  vente:%s  march:%s  => %s (%s)",
    ns.ItemName(itemID), ns.Money(p.market), fmtRate(p.saleRate),
    ns.Money(p.vendor), ns.Money(p.best), p.bestSource or "?")
end

local function safePrices(id)
  local ok, p = pcall(ns.Prices.Get, id)
  if ok then return p end
  ns.Print("|cffff4444Erreur prix " .. id .. " :|r " .. tostring(p))
  return {}
end

-- /pogrind : les objets farmables les plus chers, avec leur meilleure zone
local function scanAll()
  local rows = {}
  for id in pairs(ns.FarmDB or {}) do
    local p = safePrices(id)
    if p.best then rows[#rows + 1] = { id = id, p = p } end
  end
  table.sort(rows, function(a, b) return a.p.best > b.p.best end)
  ns.Print(string.format("Top %d des ressources farmables (sur %d connues) :", math.min(TOP, #rows), #rows))
  for i = 1, math.min(TOP, #rows) do
    local r = rows[i]
    local ok, err = pcall(function()
      local z = ns.BestZone(r.id)
      ns.Print(i .. ". " .. priceLine(r.id, r.p))
      if z then ns.Print("     |cffaaaaaa-> " .. ns.FormatZone(z) .. "|r") end
    end)
    if not ok then ns.Print("|cffff4444Erreur sur " .. r.id .. " :|r " .. tostring(err)) end
  end
end

-- /pogrind <objet> : prix + toutes les zones connues
local function showItem(id)
  ns.Print(priceLine(id, safePrices(id)))
  local zones = ns.FarmDB and ns.FarmDB[id]
  if not zones then
    ns.Print("Aucune zone de farm connue pour cet objet.")
    return
  end
  for i, z in ipairs(zones) do
    ns.Print("  " .. i .. ". " .. ns.FormatZone(z))
  end
end

SLASH_POGRIND1 = "/pogrind"
SlashCmdList.POGRIND = function(msg)
  msg = strtrim(msg or "")
  if msg == "" then
    scanAll()
    return
  end
  if msg == "log" then
    ns.LootLog.Report()
    return
  end
  local id = tonumber(msg) or ns.GetItemInfoInstant(msg)
  if id then
    showItem(id)
  else
    ns.Print("Usage : /pogrind  |  /pogrind <itemID ou lien>  |  /pogrind log")
  end
end
