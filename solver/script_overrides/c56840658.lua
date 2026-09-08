-- YGO Reborn reviewed override for Project Ignis official/c56840658.lua
-- Poison Draw Frog (56840658)
--
-- Upstream baseline reviewed: ProjectIgnis/CardScripts
--   14064037f42d0ae0bb9f8577d7eba2baad95e633
--
-- Current TCG English text explicitly excludes the case where this card was
-- attacked while face-down and then destroyed by battle. Official Japanese OCG
-- Q&A instead allows the draw in that case because the monster is flipped
-- face-up before battle destruction. Reborn uses the current TCG rules/text
-- authority, so the OCG-oriented upstream previous-face-up check is insufficient.
--
-- Reborn correction: record whether this exact card was face-down when it became
-- an attack target. Suppress the GY draw only when that flag is still present AND
-- the card was sent to the GY by battle. A later attack while the card is face-up
-- clears the flag. Non-battle sends still draw normally, including after an
-- earlier canceled attack. The flag intentionally does not use RESET_EVENT so it
-- survives the battle flip and movement to the GY long enough for EVENT_TO_GRAVE.

--引きガエル
--Poison Draw Frog
local s,id=GetID()
function s.initial_effect(c)
	--Remember whether this card was face-down when selected as an attack target
	local e1=Effect.CreateEffect(c)
	e1:SetType(EFFECT_TYPE_SINGLE+EFFECT_TYPE_CONTINUOUS)
	e1:SetProperty(EFFECT_FLAG_CANNOT_DISABLE)
	e1:SetCode(EVENT_BE_BATTLE_TARGET)
	e1:SetOperation(s.regop)
	c:RegisterEffect(e1)
	--Draw 1 card when sent from the field to the GY, except the TCG face-down battle case
	local e2=Effect.CreateEffect(c)
	e2:SetDescription(aux.Stringid(id,0))
	e2:SetCategory(CATEGORY_DRAW)
	e2:SetType(EFFECT_TYPE_SINGLE+EFFECT_TYPE_TRIGGER_O)
	e2:SetProperty(EFFECT_FLAG_DAMAGE_STEP)
	e2:SetRange(LOCATION_MZONE)
	e2:SetCode(EVENT_TO_GRAVE)
	e2:SetCondition(s.condition)
	e2:SetTarget(s.target)
	e2:SetOperation(s.operation)
	c:RegisterEffect(e2)
end
function s.regop(e,tp,eg,ep,ev,re,r,rp)
	local c=e:GetHandler()
	--A new attack target declaration replaces any earlier target-state record.
	c:ResetFlagEffect(id)
	if c:IsFacedown() then
		c:RegisterFlagEffect(id,RESET_PHASE|PHASE_BATTLE,0,1)
	end
end
function s.condition(e,tp,eg,ep,ev,re,r,rp)
	local c=e:GetHandler()
	return c:IsPreviousLocation(LOCATION_ONFIELD) and c:IsPreviousPosition(POS_FACEUP)
		and not (c:IsReason(REASON_BATTLE) and c:GetFlagEffect(id)>0)
end
function s.target(e,tp,eg,ep,ev,re,r,rp,chk,chkc)
	if chk==0 then return Duel.IsPlayerCanDraw(tp,1) end
	Duel.SetTargetPlayer(tp)
	Duel.SetTargetParam(1)
	Duel.SetOperationInfo(0,CATEGORY_DRAW,nil,0,tp,1)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
	local p,d=Duel.GetChainInfo(0,CHAININFO_TARGET_PLAYER,CHAININFO_TARGET_PARAM)
	Duel.Draw(p,d,REASON_EFFECT)
end
