local ADDON, ns = ...
ns.name = ADDON

local defaults = {
  minSaleRate = 0.05, -- en dessous, l'objet ne se vend pas : on l'ignore côté HV
}

function ns.Print(...)
  print("|cff33ff99PoGrinder|r:", ...)
end

-- Compat : selon la version du client, ces fonctions sont dans C_Item ou globales
local CI = C_Item or {}
ns.GetItemInfo = CI.GetItemInfo or GetItemInfo
ns.GetItemInfoInstant = CI.GetItemInfoInstant or GetItemInfoInstant
ns.RequestItem = CI.RequestLoadItemDataByID or function() end

function ns.Money(copper)
  if not copper or copper <= 0 then return "-" end
  copper = math.floor(copper)
  if GetCoinTextureString then return GetCoinTextureString(copper) end
  return string.format("%dg %ds %dc", copper / 10000, (copper / 100) % 100, copper % 100)
end

local f = CreateFrame("Frame")
f:RegisterEvent("ADDON_LOADED")
f:RegisterEvent("PLAYER_LOGIN")
f:SetScript("OnEvent", function(_, event, arg1)
  if event == "ADDON_LOADED" and arg1 == ADDON then
    PoGrinderDB = PoGrinderDB or {}
    for k, v in pairs(defaults) do
      if PoGrinderDB[k] == nil then PoGrinderDB[k] = v end
    end
    ns.db = PoGrinderDB
  elseif event == "PLAYER_LOGIN" then
    if ns.Prices.IsTSMAvailable() then
      ns.Print("TSM détecté. Tape /pogrind pour tester.")
    else
      ns.Print("TSM introuvable : seuls les prix marchand seront disponibles.")
    end
  end
end)
