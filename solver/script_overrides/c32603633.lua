-- YGO Reborn TCG-specific reviewed override for Project Ignis official/c32603633.lua
-- Backs to the Wall (32603633)
--
-- Upstream baseline: ProjectIgnis/CardScripts
--   14064037f42d0ae0bb9f8577d7eba2baad95e633
--
-- Current TCG English text:
-- "Pay LP so that you only have 100 left; Special Summon as many \"Six Samurai\"
-- monsters with different names from your GY as possible. You cannot Special
-- Summon a monster with the same name as a monster you already control."
--
-- Current Japanese OCG text/Q&A instead treats a same-name card anywhere on the
-- field as blocking that Special Summon. Upstream implements that OCG behavior by
-- searching both players' entire on-field locations.
--
-- Reborn uses current TCG text as authority. This override changes only that
-- duplicate-name gate: a same-name face-up monster in the activating player's
-- Monster Zone blocks the summon; the opponent's field and the activating
-- player's Spell & Trap Zone do not. The rest of the upstream operation is kept.

--究極・背水の陣
--Backs to the Wall
local s,id=GetID()
function s.initial_effect(c)
	--Activate
	local e1=Effect.CreateEffect(c)
	e1:SetType(EFFECT_TYPE_ACTIVATE)
	e1:SetCategory(CATEGORY_SPECIAL_SUMMON)
	e1:SetCode(EVENT_FREE_CHAIN)
	e1:SetCost(s.cost)
	e1:SetTarget(s.tg)
	e1:SetOperation(s.op)
	c:RegisterEffect(e1)
end
s.listed_series={SET_SIX_SAMURAI}
function s.cost(e,tp,eg,ep,ev,re,r,rp,chk)
	if chk==0 then return Duel.GetLP(tp)>100 end
	Duel.PayLPCost(tp,Duel.GetLP(tp)-100)
end
function s.filter(c,e,tp)
	return c:IsSetCard(SET_SIX_SAMURAI) and c:IsCanBeSpecialSummoned(e,0,tp,false,false)
		and not Duel.IsExistingMatchingCard(aux.FaceupFilter(Card.IsCode,c:GetCode()),tp,LOCATION_MZONE,0,1,nil)
end
function s.tg(e,tp,eg,ep,ev,re,r,rp,chk)
	if chk==0 then return Duel.GetLocationCount(tp,LOCATION_MZONE)>0
		and Duel.IsExistingMatchingCard(s.filter,tp,LOCATION_GRAVE,0,1,nil,e,tp) end
	Duel.SetOperationInfo(0,CATEGORY_SPECIAL_SUMMON,nil,1,tp,LOCATION_GRAVE)
end
function s.op(e,tp,eg,ep,ev,re,r,rp)
	local ft=Duel.GetLocationCount(tp,LOCATION_MZONE)
	if ft<=0 then return end
	if Duel.IsPlayerAffectedByEffect(tp,CARD_BLUEEYES_SPIRIT) then ft=1 end
	local g=Duel.GetMatchingGroup(s.filter,tp,LOCATION_GRAVE,0,nil,e,tp)
	while #g>0 and ft>0 do
		Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_SPSUMMON)
		local sg=g:Select(tp,1,1,nil)
		Duel.SpecialSummonStep(sg:GetFirst(),0,tp,tp,false,false,POS_FACEUP)
		ft=ft-1
		g:Remove(Card.IsCode,nil,sg:GetFirst():GetCode())
	end
	Duel.SpecialSummonComplete()
end
