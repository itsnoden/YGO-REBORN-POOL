-- YGO Reborn reviewed override for Project Ignis official/c24096228.lua
-- Double Spell (24096228)
--
-- Upstream baseline: ProjectIgnis/CardScripts
--   49b0af044cebcb92f3f23211ef436971e1fc16fb
-- Current upstream was also checked on 2026-09-07 and still had the same
-- recursive CheckActivateEffect behavior.
--
-- Latest official English text was verified against the Yu-Gi-Oh! TCG Card
-- Database (Double Spell, cid=5629). This override does not change the card's
-- intended targets/cost/operation. It only guards activation-legality probing
-- when a Double Spell in the opponent's GY is itself being considered as the
-- Spell copied by another Double Spell.
--
-- Without the guard, CheckActivateEffect on that GY Double Spell can re-enter
-- this same target filter indefinitely (observed deterministic C stack overflow
-- in Reborn held-out candidate 593df70fb35282f5, seed 21101). The guard breaks
-- only the cyclic probe. Other Spells in the GY are still tested normally, so a
-- GY Double Spell remains selectable when its copied effect has a real legal
-- downstream Spell to use.

--二重魔法
--Double Spell
local s,id=GetID()
local checking_double_spell=false
function s.initial_effect(c)
	--copy spell
	local e1=Effect.CreateEffect(c)
	e1:SetType(EFFECT_TYPE_ACTIVATE)
	e1:SetCode(EVENT_FREE_CHAIN)
	e1:SetProperty(EFFECT_FLAG_CARD_TARGET)
	e1:SetCost(s.cost)
	e1:SetTarget(s.target)
	e1:SetOperation(s.operation)
	c:RegisterEffect(e1)
end
s.listed_series={SET_RANK_UP_MAGIC}
function s.cfilter(c)
	return c:IsDiscardable() and c:IsSpell()
end
function s.cost(e,tp,eg,ep,ev,re,r,rp,chk)
	if chk==0 then return Duel.IsExistingMatchingCard(s.cfilter,tp,LOCATION_HAND,0,1,e:GetHandler()) end
	Duel.DiscardHand(tp,s.cfilter,1,1,REASON_COST|REASON_DISCARD)
end

-- CheckActivateEffect normally validates whether the opponent-GY Spell can be
-- used. For Double Spell itself, that validation executes this target function
-- again. A single recursion guard is sufficient because every nested Double
-- Spell is searching the same opponent GY for an eventual non-cyclic Spell.
function s.checkactivate(c)
	if c:IsCode(id) and checking_double_spell then return nil end
	local guarded=c:IsCode(id)
	if guarded then checking_double_spell=true end
	local te=c:CheckActivateEffect(false,false,false)
	if guarded then checking_double_spell=false end
	return te
end
function s.filter1(c,e,tp,eg,ep,ev,re,r,rp)
	local te=s.checkactivate(c)
	if c:IsSpell() and te then
		if c:IsSetCard(SET_RANK_UP_MAGIC) then
			local tg=te:GetTarget()
			return not tg or tg(e,tp,eg,ep,ev,re,r,rp,0)
		else
			return true
		end
	end
	return false
end
function s.filter2(c,e,tp,eg,ep,ev,re,r,rp)
	local te=s.checkactivate(c)
	if c:IsSpell() and not c:IsType(TYPE_EQUIP|TYPE_CONTINUOUS) and te then
		if c:IsSetCard(SET_RANK_UP_MAGIC) then
			local tg=te:GetTarget()
			return not tg or tg(e,tp,eg,ep,ev,re,r,rp,0)
		else
			return true
		end
	end
	return false
end
function s.target(e,tp,eg,ep,ev,re,r,rp,chk,chkc)
	if chkc then return false end
	if chk==0 then
		local b=e:GetHandler():IsLocation(LOCATION_HAND)
		local ft=Duel.GetLocationCount(tp,LOCATION_SZONE)
		if (b and ft>1) or (not b and ft>0) then
			return Duel.IsExistingTarget(s.filter1,tp,0,LOCATION_GRAVE,1,e:GetHandler(),e,tp,eg,ep,ev,re,r,rp)
		else
			return Duel.IsExistingTarget(s.filter2,tp,0,LOCATION_GRAVE,1,e:GetHandler(),e,tp,eg,ep,ev,re,r,rp)
		end
	end
	Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_TARGET)
	if Duel.GetLocationCount(tp,LOCATION_SZONE)>0 then
		Duel.SelectTarget(tp,s.filter1,tp,0,LOCATION_GRAVE,1,1,nil,e,tp,eg,ep,ev,re,r,rp)
	else
		Duel.SelectTarget(tp,s.filter2,tp,0,LOCATION_GRAVE,1,1,nil,e,tp,eg,ep,ev,re,r,rp)
	end
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
	local tc=Duel.GetFirstTarget()
	if not tc or not tc:IsRelateToEffect(e) then return end
	local tpe=tc:GetType()
	local te=tc:GetActivateEffect()
	local tg=te:GetTarget()
	local co=te:GetCost()
	local op=te:GetOperation()
	e:SetCategory(te:GetCategory())
	e:SetProperty(te:GetProperty())
	Duel.ClearTargetCard()
	if (tpe&TYPE_EQUIP+TYPE_CONTINUOUS)~=0 or tc:IsHasEffect(EFFECT_REMAIN_FIELD) then
		if Duel.GetLocationCount(tp,LOCATION_SZONE)<=0 then return end
		Duel.MoveToField(tc,tp,tp,LOCATION_SZONE,POS_FACEUP,true)
	elseif (tpe&TYPE_FIELD)~=0 then
		Duel.MoveToField(tc,tp,tp,LOCATION_FZONE,POS_FACEUP,true)
	end
	tc:CreateEffectRelation(te)
	if co then co(te,tp,eg,ep,ev,re,r,rp,1) end
	if tg then
		if tc:IsSetCard(SET_RANK_UP_MAGIC) then
			tg(e,tp,eg,ep,ev,re,r,rp,1)
		else
			tg(te,tp,eg,ep,ev,re,r,rp,1)
		end
	end
	Duel.BreakEffect()
	local g=Duel.GetChainInfo(0,CHAININFO_TARGET_CARDS)
	local etc=g:GetFirst()
	for etc in aux.Next(g) do
		etc:CreateEffectRelation(te)
	end
	if op then
		if tc:IsSetCard(SET_RANK_UP_MAGIC) then
			op(e,tp,eg,ep,ev,re,r,rp)
		else
			op(te,tp,eg,ep,ev,re,r,rp)
		end
	end
	tc:ReleaseEffectRelation(te)
	etc=g:GetFirst()
	for etc in aux.Next(g) do
		etc:ReleaseEffectRelation(te)
	end
end
