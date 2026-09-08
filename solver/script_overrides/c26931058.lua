-- YGO Reborn reviewed override for Project Ignis official/c26931058.lua
-- Formation Union (26931058)
--
-- Upstream baseline reviewed: ProjectIgnis/CardScripts
--   14064037f42d0ae0bb9f8577d7eba2baad95e633
--
-- Current official English text (Yu-Gi-Oh! TCG Card Database, cid=5623):
-- "Activate 1 of the following effects.
--  ●Target 1 face-up Union monster you control; equip it to 1 appropriate monster you control.
--  ●Unequip 1 Union monster you control that is an Equip Card and Special Summon it in Attack Position."
--
-- Upstream incorrectly gives the activation a permanent CARD_TARGET property,
-- targets both the Union monster and its equip recipient in mode 1, and targets
-- the equipped Union in mode 2. Current PSCT targets only the Union monster in
-- mode 1; the recipient is chosen while resolving. Mode 2 does not target, so
-- its Union monster is likewise chosen while resolving.
--
-- Reborn correction: make targeting mode-dependent, target exactly one Union in
-- mode 1, and use non-targeting resolution-time selection for the equip recipient
-- and for mode 2. No other Union/equip legality checks are changed.

--フォーメーション・ユニオン
--Formation Union
local s,id=GetID()
function s.initial_effect(c)
	--Activate
	local e1=Effect.CreateEffect(c)
	e1:SetDescription(aux.Stringid(id,0))
	e1:SetType(EFFECT_TYPE_ACTIVATE)
	e1:SetCode(EVENT_FREE_CHAIN)
	e1:SetHintTiming(0,TIMING_MAIN_END|TIMINGS_CHECK_MONSTER_E)
	e1:SetTarget(s.target)
	e1:SetOperation(s.activate)
	c:RegisterEffect(e1)
end
s.listed_card_types={TYPE_UNION}
function s.unioneqfilter(c,tp)
	return c:IsType(TYPE_UNION) and c:IsFaceup()
		and Duel.IsExistingMatchingCard(s.eqfilter,tp,LOCATION_MZONE,0,1,c,c)
end
function s.eqfilter(c,ec)
	return ec:CheckUnionTarget(c) and aux.CheckUnionEquip(ec,c) and c:IsFaceup()
end
function s.spfilter(c,e,tp)
	return c:IsHasEffect(EFFECT_UNION_STATUS) and c:IsFaceup() and c:IsCanBeSpecialSummoned(e,0,tp,false,false,POS_FACEUP_ATTACK)
end
function s.target(e,tp,eg,ep,ev,re,r,rp,chk,chkc)
	if chkc then return e:GetLabel()==1 and chkc:IsControler(tp) and chkc:IsLocation(LOCATION_MZONE) and s.unioneqfilter(chkc,tp) end
	local b1=Duel.GetLocationCount(tp,LOCATION_SZONE)>0
		and Duel.IsExistingTarget(s.unioneqfilter,tp,LOCATION_MZONE,0,1,nil,tp)
	local b2=Duel.GetLocationCount(tp,LOCATION_MZONE)>0
		and Duel.IsExistingMatchingCard(s.spfilter,tp,LOCATION_STZONE,0,1,nil,e,tp)
	if chk==0 then return b1 or b2 end
	local op=Duel.SelectEffect(tp,
		{b1,aux.Stringid(id,1)},
		{b2,aux.Stringid(id,2)})
	e:SetLabel(op)
	if op==1 then
		e:SetCategory(CATEGORY_EQUIP)
		e:SetProperty(EFFECT_FLAG_CARD_TARGET)
		Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_EQUIP)
		local g=Duel.SelectTarget(tp,s.unioneqfilter,tp,LOCATION_MZONE,0,1,1,nil,tp)
		Duel.SetOperationInfo(0,CATEGORY_EQUIP,g,1,tp,0)
	elseif op==2 then
		e:SetCategory(CATEGORY_SPECIAL_SUMMON)
		Duel.SetOperationInfo(0,CATEGORY_SPECIAL_SUMMON,nil,1,tp,LOCATION_STZONE)
	end
end
function s.activate(e,tp,eg,ep,ev,re,r,rp)
	local op=e:GetLabel()
	if op==1 then
		--Target 1 Union monster; choose its appropriate equip recipient on resolution
		local ec=Duel.GetFirstTarget()
		if not (ec and ec:IsRelateToEffect(e) and ec:IsControler(tp) and ec:IsFaceup()) then return end
		if Duel.GetLocationCount(tp,LOCATION_SZONE)<=0 then return end
		local g=Duel.GetMatchingGroup(s.eqfilter,tp,LOCATION_MZONE,0,ec,ec)
		if #g==0 then return end
		Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_EQUIP)
		local tc=Duel.SelectMatchingCard(tp,s.eqfilter,tp,LOCATION_MZONE,0,1,1,ec,ec):GetFirst()
		if tc and aux.CheckUnionEquip(ec,tc) and Duel.Equip(tp,ec,tc) then
			aux.SetUnionState(ec)
		end
	elseif op==2 then
		--Non-targeting: choose an equipped Union monster on resolution and Special Summon it
		if Duel.GetLocationCount(tp,LOCATION_MZONE)<=0 then return end
		local g=Duel.GetMatchingGroup(s.spfilter,tp,LOCATION_STZONE,0,nil,e,tp)
		if #g==0 then return end
		Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_SPSUMMON)
		local tc=Duel.SelectMatchingCard(tp,s.spfilter,tp,LOCATION_STZONE,0,1,1,nil,e,tp):GetFirst()
		if tc then
			Duel.SpecialSummon(tc,0,tp,tp,false,false,POS_FACEUP_ATTACK)
		end
	end
end
