"""
ai_engine.py — Adaptive AI Interview Engine
Uses OpenRouter (arcee-ai/trinity-large-preview:free) to:
  1. Generate contextually adaptive questions
  2. Evaluate candidate responses
  3. Decide next difficulty / topic
"""

import requests
import json
import re
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, LLM_MODEL, FALLBACK_QUESTIONS
from config import DIFFICULTY_INCREASE_THRESHOLD, DIFFICULTY_DECREASE_THRESHOLD


# ─────────────────────────────────────────────────────────────
# CORE LLM CALL
# ─────────────────────────────────────────────────────────────
def call_llm(messages: list, temperature: float = 0.7, max_tokens: int = 1024) -> str:
    """Send messages to OpenRouter LLM and return the reply string."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5055",
        "X-Title": "AI Interview Platform"
    }
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        response = requests.post(OPENROUTER_BASE_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[AI Engine] LLM call failed: {e}")
        return None


def _safe_json(text: str) -> dict:
    """Extract JSON from LLM output safely."""
    if not text:
        return {}
    # Try to find JSON block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return {}


# ─────────────────────────────────────────────────────────────
# GENERATE FIRST QUESTION
# ─────────────────────────────────────────────────────────────
def generate_opening_question(session_type: str, candidate_name: str, role: str = "Software Engineer") -> dict:
    """Generate the opening interview question based on session type."""

    # Phase-specific instructions
    phase_instructions = {
        "communication": """This is a COMMUNICATION assessment (Phase 1).
Focus on English communication skills, articulation, clarity of thought, professional expression.
Ask questions that require the candidate to explain, describe, articulate, or discuss.
Topics: self-introduction, explaining concepts to non-technical people, describing work experiences, presenting ideas.
DO NOT ask coding or algorithm questions. Focus purely on communication ability.""",

        "aptitude": """This is a pure APTITUDE test (Phase 2).
Focus on logical reasoning, quantitative analysis, problem-solving, pattern recognition, and critical thinking.
Ask questions involving: number series, logical puzzles, probability, percentages, ratios, deductive reasoning.
DO NOT ask coding questions. These are pen-and-paper style aptitude problems.""",

        "coding": """This is an ADVANCED CODING round (Phase 3).
Focus on data structures, algorithms, system design, and complex programming problems.
Difficulty: MODERATE to TOUGH (advanced level).
Ask questions about: dynamic programming, graph algorithms, tree traversals, system design, time complexity optimization.
Questions should require actual code implementation or detailed algorithmic thinking.""",

        "technical": "For Technical: start with a foundational concept question.",
        "behavioral": "For Behavioral: start with a broad situational STAR-method question.",
        "mock": "For Mock: start with an introduction question."
    }

    instruction = phase_instructions.get(session_type, phase_instructions.get("technical", ""))

    system_prompt = f"""You are an expert AI interviewer conducting a {session_type} interview for a {role} position.
Your job is to ask one opening question that is warm, professional, and appropriate for the session type.

{instruction}

Respond ONLY in this JSON format:
{{
  "question": "Your question here",
  "topic": "Topic name",
  "difficulty": 1,
  "type": "text|code|verbal",
  "hint": "Optional helpful hint for the candidate",
  "follow_up_angle": "What aspect to probe if answer is weak"
}}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Start the interview. Candidate name: {candidate_name}. Session: {session_type}."}
    ]

    result = call_llm(messages, temperature=0.6)
    parsed = _safe_json(result)

    if not parsed or "question" not in parsed:
        # Fallback
        fallback = FALLBACK_QUESTIONS.get(session_type, FALLBACK_QUESTIONS.get("mock", FALLBACK_QUESTIONS["technical"]))[0]
        return {
            "question": fallback["q"],
            "topic": fallback["topic"],
            "difficulty": fallback["difficulty"],
            "type": "text",
            "hint": "",
            "follow_up_angle": "depth of understanding"
        }

    return parsed


# ─────────────────────────────────────────────────────────────
# EVALUATE ANSWER + GENERATE NEXT QUESTION
# ─────────────────────────────────────────────────────────────
def evaluate_and_adapt(
    session_type: str,
    conversation_history: list,
    current_question: dict,
    candidate_answer: str,
    answer_type: str,   # "text", "code", "verbal"
    question_num: int,
    role: str = "Software Engineer"
) -> dict:
    """
    Evaluate the candidate's answer and decide the next action.
    Strictly prevents repeated questions by passing all prior Q&A to the LLM.
    """

    # ── Build previous-questions context ──────────────────────
    covered_topics = list(set(item.get("topic", "") for item in conversation_history if item.get("topic")))
    asked_questions = [item.get("question", "")[:120] for item in conversation_history]

    no_repeat_block = ""
    if asked_questions:
        no_repeat_block = (
            "\n\n⚠️ CRITICAL RULE — DO NOT REPEAT: The following questions have ALREADY been asked. "
            "You MUST ask a completely different question on a NEW topic:\n"
            + "\n".join(f"  {i+1}. {q}" for i, q in enumerate(asked_questions))
            + f"\n\nTopics already covered: {', '.join(covered_topics) if covered_topics else 'none yet'}."
            "\nChoose a topic that has NOT been covered yet."
        )

    # Phase-specific evaluation context
    phase_context = {
        "communication": "This is a COMMUNICATION round. Questions must test English fluency, articulation, clarity. NO coding questions.",
        "aptitude": "This is an APTITUDE round. Questions must test logical reasoning, math, patterns, critical thinking. NO coding questions.",
        "coding": "This is an ADVANCED CODING round. Questions must be moderate-to-tough: DS&A, system design, DP, graphs. Require code.",
    }
    phase_note = phase_context.get(session_type, "")

    system_prompt = f"""You are an expert AI interviewer and evaluator for a {role} {session_type} interview.
You have asked a question and received a candidate answer.
{phase_note}

Your tasks:
1. EVALUATE the answer objectively (score 0-100 across dimensions)
2. DECIDE the next action (harder/easier/clarify/new_topic)
3. GENERATE the NEXT question — which must be on a BRAND NEW topic not yet covered
{no_repeat_block}

SCORING DIMENSIONS:
- correctness: Technical accuracy (0-100)
- communication: Clarity, structure, articulation (0-100)
- depth: Level of detail and nuance (0-100)
- confidence: Confidence indicators in response (0-100)
- overall: Weighted average

ADAPTATION RULES:
- overall > {DIFFICULTY_INCREASE_THRESHOLD}: Increase difficulty, choose a harder new topic
- overall < {DIFFICULTY_DECREASE_THRESHOLD}: Lower difficulty on a new topic
- Unclear answer: Ask to rephrase on the same topic (only once, then move on)
- Very good: Acknowledge briefly, probe deeper OR pick an advanced new topic

Respond ONLY in this EXACT JSON format (no markdown, no extra text):
{{
  "evaluation": {{
    "correctness": 75,
    "communication": 80,
    "depth": 65,
    "confidence": 70,
    "overall": 72,
    "feedback_summary": "One sentence on what was good/weak",
    "strength": "Key strength in the answer",
    "weakness": "Key gap or area to improve",
    "action_taken": "harder|easier|clarify|new_topic"
  }},
  "next_question": {{
    "question": "Your completely new question here on a NEW topic",
    "topic": "New Topic Name (must differ from: {', '.join(covered_topics) if covered_topics else 'none'})",
    "difficulty": 2,
    "type": "text|code|verbal",
    "hint": "Optional brief hint",
    "transition": "One professional sentence bridging from last answer to next question"
  }}
}}"""

    # Build recent conversation snippet
    history_text = ""
    for item in conversation_history[-3:]:
        history_text += f"Q: {item.get('question','')}\nA: {item.get('answer','')[:300]}\n\n"

    user_prompt = f"""Recent exchanges:
{history_text}
Current Question (#{question_num}): {current_question.get('question','')}
Topic: {current_question.get('topic','')}
Difficulty: {current_question.get('difficulty', 1)}
Answer Type: {answer_type}

Candidate's Answer:
\"\"\"
{candidate_answer[:2000]}
\"\"\"

Evaluate this answer and generate the NEXT question on a brand new topic."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    result = call_llm(messages, temperature=0.5, max_tokens=1400)
    parsed = _safe_json(result)

    # Validate that the next question is truly different
    if parsed and "next_question" in parsed:
        next_q_text = parsed["next_question"].get("question", "").strip()
        # If the next question is too similar to any previous one, override with fallback
        for prev_q in asked_questions:
            if prev_q[:60].lower() in next_q_text.lower() or next_q_text[:60].lower() in prev_q.lower():
                parsed = {}  # Force fallback
                break

    if not parsed or "evaluation" not in parsed:
        # Fallback: pick a question from the bank that hasn't been asked
        fallback_qs = FALLBACK_QUESTIONS.get(session_type, FALLBACK_QUESTIONS["mock"])
        unused = [q for q in fallback_qs if not any(q["q"][:40] in aq for aq in asked_questions)]
        if not unused:
            # All fallbacks used — generate a generic one
            unused = [{"q": f"Can you walk me through your approach to solving a {session_type} problem step by step?",
                       "topic": "Problem Solving", "difficulty": 2}]
        chosen = unused[min(len(unused)-1, question_num % len(unused))]
        return {
            "evaluation": {
                "correctness": 65, "communication": 65, "depth": 60,
                "confidence": 70, "overall": 65,
                "feedback_summary": "Answer received and noted.",
                "strength": "Engaged with the question.",
                "weakness": "Could provide more detail.",
                "action_taken": "new_topic"
            },
            "next_question": {
                "question": chosen["q"],
                "topic": chosen["topic"],
                "difficulty": chosen["difficulty"],
                "type": "text",
                "hint": "",
                "transition": "Let's move on to a different topic."
            }
        }

    return parsed



# ─────────────────────────────────────────────────────────────
# GENERATE FINAL SUMMARY EVALUATION
# ─────────────────────────────────────────────────────────────
def generate_final_report(session_type: str, conversation_history: list,
                           candidate_name: str, role: str = "Software Engineer") -> dict:
    """Generate the final structured multi-factor assessment report."""

    system_prompt = f"""You are an expert interview evaluator. 
You have conducted a complete {session_type} interview for a {role} position with {candidate_name}.

Review ALL question-answer pairs and create a comprehensive final assessment report.

Respond ONLY in this JSON format:
{{
  "overall_score": 78,
  "recommendation": "Strong Consider|Consider|Borderline|Reject",
  "summary": "2-3 sentence overall summary of the candidate",
  "categories": {{
    "technical_knowledge": {{"score": 80, "notes": "..."}},
    "problem_solving": {{"score": 75, "notes": "..."}},
    "communication": {{"score": 70, "notes": "..."}},
    "depth_of_answers": {{"score": 72, "notes": "..."}},
    "confidence": {{"score": 68, "notes": "..."}}
  }},
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "areas_for_improvement": ["area 1", "area 2"],
  "topics_covered": ["topic1", "topic2", "topic3"],
  "decision_logic": "Transparent explanation of how scores were derived",
  "limitations": "Any limitations in this AI assessment (e.g., verbal accent, answer length bias)",
  "candidate_feedback": "Constructive feedback for the candidate to improve",
  "recruiter_notes": "Private notes for the recruiter about hiring suitability"
}}"""

    qa_text = ""
    for i, item in enumerate(conversation_history, 1):
        qa_text += f"Q{i} ({item.get('topic','')}, Difficulty {item.get('difficulty',1)}): {item.get('question','')}\n"
        qa_text += f"A{i}: {item.get('answer','')}\n"
        qa_text += f"Score: {item.get('overall_score', 'N/A')}\n\n"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Full interview transcript:\n\n{qa_text}"}
    ]

    result = call_llm(messages, temperature=0.3, max_tokens=2000)
    parsed = _safe_json(result)

    if not parsed:
        # Compute basic fallback report from stored scores
        scores = [item.get("overall_score", 65) for item in conversation_history if item.get("overall_score")]
        avg = int(sum(scores) / len(scores)) if scores else 65
        return {
            "overall_score": avg,
            "recommendation": "Consider" if avg >= 65 else "Borderline",
            "summary": f"{candidate_name} completed the {session_type} interview with an average score of {avg}%.",
            "categories": {
                "technical_knowledge": {"score": avg, "notes": "Based on session responses."},
                "problem_solving": {"score": avg, "notes": "Based on session responses."},
                "communication": {"score": avg, "notes": "Based on session responses."},
                "depth_of_answers": {"score": avg, "notes": "Based on session responses."},
                "confidence": {"score": avg, "notes": "Based on session responses."}
            },
            "strengths": ["Completed the full interview", "Engaged with all questions"],
            "areas_for_improvement": ["Provide more detailed answers", "Use specific examples"],
            "topics_covered": list(set(item.get("topic", "") for item in conversation_history)),
            "decision_logic": "Scores averaged across all question evaluations.",
            "limitations": "AI assessment may not fully capture nuanced verbal communication styles.",
            "candidate_feedback": "Review your answers and practice providing more structured, detailed responses.",
            "recruiter_notes": f"Average performance across {len(conversation_history)} questions."
        }

    return parsed
