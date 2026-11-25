local _, ns = ...
local Prices = {}
ns.Prices = Prices

function Prices.IsTSMAvailable()
  return type(TSM_API) == "table" and type(TSM_API.GetCustomPriceValue) == "function"
end

local function tsm(source, itemID)
  if not Prices.IsTSMAvailable() then return nil end
  local ok, value = pcall(TSM_API.GetCustomPriceValue, source, "i:" .. itemID)
  if ok then return value end
  return nil
end

-- Prix marchand : TSM d'abord, sinon l'info Blizzard (si l'objet est en cache)
function Prices.Vendor(itemID)
  local v = tsm("VendorSell", itemID)
  if v then return v end
  local sell = select(11, ns.GetItemInfo(itemID))
  return sell and sell > 0 and sell or nil
end

-- Renvoie une table { market, minBuyout, saleRate, soldPerDay, vendor, best, bestSource }
function Prices.Get(itemID)
  local p = {
    market     = tsm("DBMarket", itemID),
    minBuyout  = tsm("DBMinBuyout", itemID),
    regionAvg  = tsm("DBRegionMarketAvg", itemID),
    saleRate   = tsm("DBRegionSaleRate", itemID), -- TSM renvoie une valeur *1000 ? voir Normalize
    soldPerDay = tsm("DBRegionSoldPerDay", itemID),
    vendor     = Prices.Vendor(itemID),
  }
  p.saleRate = Prices.NormalizeRate(p.saleRate)
  if p.saleRate == 1 then p.saleRate = nil end -- 100 % = donnée absente sur Forever

  -- Prix prudent : le plus bas entre valeur de marché et prix mini actuel
  local ah = p.market or p.regionAvg
  if ah and p.minBuyout then ah = math.min(ah, p.minBuyout) end
  p.ahSafe = ah
  local minRate = ns.db and ns.db.minSaleRate or 0.05
  if ah and p.saleRate and p.saleRate < minRate then
    ah = nil -- invendable en pratique
  end

  if ah and (not p.vendor or ah > p.vendor) then
    p.best, p.bestSource = ah, "HV"
  elseif p.vendor then
    p.best, p.bestSource = p.vendor, "Marchand"
  end
  return p
end

-- Selon les versions, TSM expose le sale rate en ratio (0.12) ou x1000 (120).
function Prices.NormalizeRate(r)
  if not r then return nil end
  if r > 1 then return r / 1000 end
  return r
end
