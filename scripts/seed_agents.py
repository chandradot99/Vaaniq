"""
Seed default agents for testing across multiple business sectors.

Usage:
    uv run python scripts/seed_agents.py --org-id <org_id>

The org_id can be found in the database or from the JWT token after logging in.
"""

import argparse
import asyncio
import uuid

from vaaniq.server.core.database import async_session_factory
# Import all models so SQLAlchemy metadata includes every table (resolves FK references)
import vaaniq.server.auth.models  # noqa: F401
from vaaniq.server.agents.models import Agent

# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

AGENTS = [
    # ------------------------------------------------------------------
    # 1. Customer Support
    # ------------------------------------------------------------------
    {
        "name": "Customer Support Agent",
        "language": "en",
        "simple_mode": False,
        "system_prompt": "You are a helpful customer support agent.",
        "graph_config": {
            "entry_point": "greet",
            "guards": [],
            "nodes": [
                {
                    "id": "greet",
                    "type": "llm_response",
                    "position": {"x": 100, "y": 200},
                    "config": {
                        "instructions": (
                            "Greet the customer warmly and ask them to describe their issue. "
                            "Be empathetic and professional."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "classify",
                    "type": "condition",
                    "position": {"x": 380, "y": 200},
                    "config": {
                        "router_prompt": (
                            "Classify the customer's issue into one of the following categories:\n"
                            "- faq: General questions answerable from the knowledge base\n"
                            "- order: Order-related issues (tracking, cancellation, returns)\n"
                            "- escalate: Complex complaints or frustrated customers requiring human help"
                        ),
                        "routes": [
                            {"label": "faq", "description": "General FAQ question"},
                            {"label": "order", "description": "Order-related issue"},
                            {"label": "escalate", "description": "Needs human agent"},
                        ],
                    },
                },
                {
                    "id": "knowledge_lookup",
                    "type": "rag_search",
                    "position": {"x": 660, "y": 80},
                    "config": {"query_template": "{{collected.issue}}"},
                },
                {
                    "id": "faq_answer",
                    "type": "llm_response",
                    "position": {"x": 940, "y": 80},
                    "config": {
                        "instructions": (
                            "Answer the customer's question using the knowledge base context. "
                            "Be concise and helpful. Ask if there's anything else you can help with."
                        ),
                        "rag_enabled": True,
                        "tools": [],
                    },
                },
                {
                    "id": "collect_order_id",
                    "type": "collect_data",
                    "position": {"x": 660, "y": 220},
                    "config": {
                        "fields": [
                            {
                                "name": "order_id",
                                "type": "string",
                                "prompt": "Please provide your order ID.",
                                "required": True,
                            },
                            {
                                "name": "issue_detail",
                                "type": "string",
                                "prompt": "Briefly describe the issue with your order.",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "id": "resolve_order",
                    "type": "llm_response",
                    "position": {"x": 940, "y": 220},
                    "config": {
                        "instructions": (
                            "Help the customer resolve their order issue. "
                            "For tracking: provide status update. "
                            "For returns: explain the return policy and next steps. "
                            "For cancellations: check if still possible and guide them."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "transfer_agent",
                    "type": "transfer_human",
                    "position": {"x": 660, "y": 360},
                    "config": {
                        "transfer_number": "+18005550100",
                        "whisper_template": (
                            "Incoming escalation from customer. Issue: {{collected.issue}}. "
                            "Handle with priority."
                        ),
                    },
                },
                {
                    "id": "end",
                    "type": "end_session",
                    "position": {"x": 1200, "y": 200},
                    "config": {
                        "farewell_message": (
                            "Thank you for contacting support. Have a great day!"
                        )
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "greet", "target": "classify"},
                {
                    "id": "e2",
                    "source": "classify",
                    "target": "knowledge_lookup",
                    "condition": "faq",
                },
                {
                    "id": "e3",
                    "source": "classify",
                    "target": "collect_order_id",
                    "condition": "order",
                },
                {
                    "id": "e4",
                    "source": "classify",
                    "target": "transfer_agent",
                    "condition": "escalate",
                },
                {"id": "e5", "source": "knowledge_lookup", "target": "faq_answer"},
                {"id": "e6", "source": "faq_answer", "target": "end"},
                {"id": "e7", "source": "collect_order_id", "target": "resolve_order"},
                {"id": "e8", "source": "resolve_order", "target": "end"},
            ],
        },
    },

    # ------------------------------------------------------------------
    # 2. Appointment Booking
    # ------------------------------------------------------------------
    {
        "name": "Appointment Booking Agent",
        "language": "en",
        "simple_mode": False,
        "system_prompt": "You are a friendly appointment scheduling assistant.",
        "graph_config": {
            "entry_point": "greet",
            "guards": [],
            "nodes": [
                {
                    "id": "greet",
                    "type": "llm_response",
                    "position": {"x": 100, "y": 200},
                    "config": {
                        "instructions": (
                            "Welcome the caller. Ask whether they want to book a new appointment, "
                            "reschedule an existing one, or cancel. Be warm and professional."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "intent_check",
                    "type": "condition",
                    "position": {"x": 380, "y": 200},
                    "config": {
                        "router_prompt": (
                            "What does the caller want to do?\n"
                            "- book: Schedule a new appointment\n"
                            "- reschedule: Change an existing appointment\n"
                            "- cancel: Cancel an existing appointment"
                        ),
                        "routes": [
                            {"label": "book", "description": "Book new appointment"},
                            {"label": "reschedule", "description": "Reschedule existing"},
                            {"label": "cancel", "description": "Cancel appointment"},
                        ],
                    },
                },
                {
                    "id": "collect_booking_details",
                    "type": "collect_data",
                    "position": {"x": 660, "y": 100},
                    "config": {
                        "fields": [
                            {
                                "name": "name",
                                "type": "string",
                                "prompt": "What is your full name?",
                                "required": True,
                            },
                            {
                                "name": "phone",
                                "type": "string",
                                "prompt": "What is your phone number?",
                                "required": True,
                            },
                            {
                                "name": "service",
                                "type": "string",
                                "prompt": "What service do you need? (e.g. consultation, follow-up, general checkup)",
                                "required": True,
                            },
                            {
                                "name": "preferred_date",
                                "type": "string",
                                "prompt": "What date works best for you? (e.g. next Monday, 15th January)",
                                "required": True,
                            },
                            {
                                "name": "preferred_time",
                                "type": "string",
                                "prompt": "What time works best? (e.g. morning, 2pm, after 4pm)",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "id": "confirm_booking",
                    "type": "http_request",
                    "position": {"x": 940, "y": 100},
                    "config": {
                        "url": "https://api.example.com/bookings",
                        "method": "POST",
                        "headers": {"Content-Type": "application/json"},
                        "body": {
                            "name": "{{collected.name}}",
                            "phone": "{{collected.phone}}",
                            "service": "{{collected.service}}",
                            "date": "{{collected.preferred_date}}",
                            "time": "{{collected.preferred_time}}",
                        },
                    },
                },
                {
                    "id": "booking_confirmed",
                    "type": "llm_response",
                    "position": {"x": 1180, "y": 100},
                    "config": {
                        "instructions": (
                            "Confirm the appointment to the caller. "
                            "Repeat the date, time and service. "
                            "Let them know they'll receive a confirmation SMS/email. "
                            "Ask if they have any other questions."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "post_booking",
                    "type": "post_session_action",
                    "position": {"x": 1180, "y": 240},
                    "config": {
                        "actions": ["send_confirmation_sms", "create_crm_contact"]
                    },
                },
                {
                    "id": "collect_existing_ref",
                    "type": "collect_data",
                    "position": {"x": 660, "y": 280},
                    "config": {
                        "fields": [
                            {
                                "name": "booking_ref",
                                "type": "string",
                                "prompt": "Please provide your booking reference number or the name used when booking.",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "id": "handle_change",
                    "type": "transfer_human",
                    "position": {"x": 940, "y": 280},
                    "config": {
                        "transfer_number": "+18005550200",
                        "whisper_template": "Caller wants to {{collected.intent}} appointment ref {{collected.booking_ref}}.",
                    },
                },
                {
                    "id": "end",
                    "type": "end_session",
                    "position": {"x": 1420, "y": 180},
                    "config": {
                        "farewell_message": "Thank you for choosing us. See you at your appointment!"
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "greet", "target": "intent_check"},
                {
                    "id": "e2",
                    "source": "intent_check",
                    "target": "collect_booking_details",
                    "condition": "book",
                },
                {
                    "id": "e3",
                    "source": "intent_check",
                    "target": "collect_existing_ref",
                    "condition": "reschedule",
                },
                {
                    "id": "e4",
                    "source": "intent_check",
                    "target": "collect_existing_ref",
                    "condition": "cancel",
                },
                {
                    "id": "e5",
                    "source": "collect_booking_details",
                    "target": "confirm_booking",
                },
                {"id": "e6", "source": "confirm_booking", "target": "booking_confirmed"},
                {"id": "e7", "source": "booking_confirmed", "target": "post_booking"},
                {"id": "e8", "source": "post_booking", "target": "end"},
                {
                    "id": "e9",
                    "source": "collect_existing_ref",
                    "target": "handle_change",
                },
                {"id": "e10", "source": "handle_change", "target": "end"},
            ],
        },
    },

    # ------------------------------------------------------------------
    # 3. Lead Qualification (Marketing / Sales)
    # ------------------------------------------------------------------
    {
        "name": "Lead Qualification Agent",
        "language": "en",
        "simple_mode": False,
        "system_prompt": "You are a sales qualification assistant.",
        "graph_config": {
            "entry_point": "greet",
            "guards": [],
            "nodes": [
                {
                    "id": "greet",
                    "type": "llm_response",
                    "position": {"x": 100, "y": 200},
                    "config": {
                        "instructions": (
                            "Introduce yourself as a product specialist. "
                            "Thank them for their interest and let them know you'd like to ask "
                            "a few quick questions to understand their needs."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "qualify",
                    "type": "collect_data",
                    "position": {"x": 380, "y": 200},
                    "config": {
                        "fields": [
                            {
                                "name": "company_name",
                                "type": "string",
                                "prompt": "What company are you from?",
                                "required": True,
                            },
                            {
                                "name": "company_size",
                                "type": "string",
                                "prompt": "How large is your team? (1-10, 11-50, 51-200, 200+)",
                                "required": True,
                            },
                            {
                                "name": "use_case",
                                "type": "string",
                                "prompt": "What are you hoping to use our product for?",
                                "required": True,
                            },
                            {
                                "name": "budget",
                                "type": "string",
                                "prompt": "Do you have a rough budget in mind for this? (Under $1k/mo, $1k-5k/mo, $5k+/mo)",
                                "required": True,
                            },
                            {
                                "name": "timeline",
                                "type": "string",
                                "prompt": "When are you looking to get started? (Immediately, 1-3 months, 3-6 months, Just exploring)",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "id": "score_lead",
                    "type": "condition",
                    "position": {"x": 680, "y": 200},
                    "config": {
                        "router_prompt": (
                            "Score this lead based on the collected data:\n"
                            "- hot: Large team (50+), budget $1k+/mo, timeline immediate or 1-3 months\n"
                            "- warm: Medium team (11-50), reasonable budget, 1-6 month timeline\n"
                            "- cold: Small team, low budget, just exploring, or vague answers"
                        ),
                        "routes": [
                            {"label": "hot", "description": "High-value lead, connect to sales immediately"},
                            {"label": "warm", "description": "Nurture with email sequence"},
                            {"label": "cold", "description": "Add to drip campaign"},
                        ],
                    },
                },
                {
                    "id": "connect_sales",
                    "type": "transfer_human",
                    "position": {"x": 960, "y": 80},
                    "config": {
                        "transfer_number": "+18005550300",
                        "whisper_template": (
                            "Hot lead: {{collected.company_name}}, {{collected.company_size}} employees, "
                            "budget {{collected.budget}}, timeline {{collected.timeline}}. "
                            "Use case: {{collected.use_case}}."
                        ),
                    },
                },
                {
                    "id": "add_to_crm_warm",
                    "type": "http_request",
                    "position": {"x": 960, "y": 220},
                    "config": {
                        "url": "https://api.example.com/crm/leads",
                        "method": "POST",
                        "headers": {"Content-Type": "application/json"},
                        "body": {
                            "company": "{{collected.company_name}}",
                            "size": "{{collected.company_size}}",
                            "budget": "{{collected.budget}}",
                            "timeline": "{{collected.timeline}}",
                            "segment": "warm",
                        },
                    },
                },
                {
                    "id": "warm_response",
                    "type": "llm_response",
                    "position": {"x": 1200, "y": 220},
                    "config": {
                        "instructions": (
                            "Thank them for their time. Let them know a product specialist will "
                            "reach out within 1-2 business days with tailored information. "
                            "Offer to send product documentation to their email."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "cold_response",
                    "type": "llm_response",
                    "position": {"x": 960, "y": 360},
                    "config": {
                        "instructions": (
                            "Thank them for their interest. Let them know you'll add them to "
                            "the newsletter with tips and product updates. "
                            "Invite them to reach out anytime they're ready to explore further."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "post_lead",
                    "type": "post_session_action",
                    "position": {"x": 1200, "y": 340},
                    "config": {"actions": ["send_nurture_email", "create_crm_lead"]},
                },
                {
                    "id": "end",
                    "type": "end_session",
                    "position": {"x": 1420, "y": 220},
                    "config": {
                        "farewell_message": "Thank you for your time! We'll be in touch soon."
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "greet", "target": "qualify"},
                {"id": "e2", "source": "qualify", "target": "score_lead"},
                {
                    "id": "e3",
                    "source": "score_lead",
                    "target": "connect_sales",
                    "condition": "hot",
                },
                {
                    "id": "e4",
                    "source": "score_lead",
                    "target": "add_to_crm_warm",
                    "condition": "warm",
                },
                {
                    "id": "e5",
                    "source": "score_lead",
                    "target": "cold_response",
                    "condition": "cold",
                },
                {"id": "e6", "source": "add_to_crm_warm", "target": "warm_response"},
                {"id": "e7", "source": "warm_response", "target": "post_lead"},
                {"id": "e8", "source": "cold_response", "target": "post_lead"},
                {"id": "e9", "source": "post_lead", "target": "end"},
                {"id": "e10", "source": "connect_sales", "target": "end"},
            ],
        },
    },

    # ------------------------------------------------------------------
    # 4. E-Commerce Order Support
    # ------------------------------------------------------------------
    {
        "name": "E-Commerce Order Support",
        "language": "en",
        "simple_mode": False,
        "system_prompt": "You are an e-commerce order support specialist.",
        "graph_config": {
            "entry_point": "greet",
            "guards": [],
            "nodes": [
                {
                    "id": "greet",
                    "type": "llm_response",
                    "position": {"x": 100, "y": 220},
                    "config": {
                        "instructions": (
                            "Greet the customer and ask how you can help with their order today. "
                            "Be friendly and efficient."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "collect_order",
                    "type": "collect_data",
                    "position": {"x": 350, "y": 220},
                    "config": {
                        "fields": [
                            {
                                "name": "order_id",
                                "type": "string",
                                "prompt": "Please provide your order number. You can find it in your confirmation email.",
                                "required": True,
                            },
                            {
                                "name": "email",
                                "type": "string",
                                "prompt": "What email address did you place the order with?",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "id": "issue_type",
                    "type": "condition",
                    "position": {"x": 620, "y": 220},
                    "config": {
                        "router_prompt": (
                            "What is the customer's issue?\n"
                            "- refund: Customer wants a refund\n"
                            "- tracking: Customer wants to track their delivery\n"
                            "- return: Customer wants to return an item\n"
                            "- other: Anything else"
                        ),
                        "routes": [
                            {"label": "refund", "description": "Refund request"},
                            {"label": "tracking", "description": "Delivery tracking"},
                            {"label": "return", "description": "Return request"},
                            {"label": "other", "description": "Other issue"},
                        ],
                    },
                },
                {
                    "id": "check_refund_eligibility",
                    "type": "run_tool",
                    "position": {"x": 880, "y": 80},
                    "config": {
                        "tool": "check_refund_eligibility",
                        "input": {
                            "order_id": "{{collected.order_id}}",
                            "email": "{{collected.email}}",
                        },
                    },
                },
                {
                    "id": "refund_eligible",
                    "type": "condition",
                    "position": {"x": 1100, "y": 80},
                    "config": {
                        "router_prompt": (
                            "Is the order eligible for a refund based on the tool result?\n"
                            "- eligible: Order is within return window and qualifies\n"
                            "- ineligible: Outside return window or already refunded"
                        ),
                        "routes": [
                            {"label": "eligible", "description": "Process refund"},
                            {"label": "ineligible", "description": "Explain policy"},
                        ],
                    },
                },
                {
                    "id": "process_refund",
                    "type": "http_request",
                    "position": {"x": 1320, "y": 40},
                    "config": {
                        "url": "https://api.example.com/refunds",
                        "method": "POST",
                        "headers": {"Content-Type": "application/json"},
                        "body": {
                            "order_id": "{{collected.order_id}}",
                            "email": "{{collected.email}}",
                        },
                    },
                },
                {
                    "id": "refund_done",
                    "type": "llm_response",
                    "position": {"x": 1540, "y": 40},
                    "config": {
                        "instructions": (
                            "Confirm that the refund has been initiated. "
                            "Let the customer know it will appear within 5-7 business days. "
                            "Apologise for any inconvenience."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "refund_denied",
                    "type": "llm_response",
                    "position": {"x": 1320, "y": 140},
                    "config": {
                        "instructions": (
                            "Apologise and explain that the order is outside the 30-day refund window "
                            "or has already been refunded. Offer store credit or escalation as alternatives."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "check_tracking",
                    "type": "run_tool",
                    "position": {"x": 880, "y": 220},
                    "config": {
                        "tool": "get_tracking_status",
                        "input": {"order_id": "{{collected.order_id}}"},
                    },
                },
                {
                    "id": "delivery_status",
                    "type": "llm_response",
                    "position": {"x": 1100, "y": 220},
                    "config": {
                        "instructions": (
                            "Share the delivery status with the customer. "
                            "Include estimated delivery date if available. "
                            "If delayed, empathise and explain."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "collect_return_reason",
                    "type": "collect_data",
                    "position": {"x": 880, "y": 360},
                    "config": {
                        "fields": [
                            {
                                "name": "return_reason",
                                "type": "string",
                                "prompt": "What is the reason for the return? (Damaged, Wrong item, Changed mind, Other)",
                                "required": True,
                            }
                        ]
                    },
                },
                {
                    "id": "generate_return_label",
                    "type": "http_request",
                    "position": {"x": 1100, "y": 360},
                    "config": {
                        "url": "https://api.example.com/returns",
                        "method": "POST",
                        "headers": {"Content-Type": "application/json"},
                        "body": {
                            "order_id": "{{collected.order_id}}",
                            "reason": "{{collected.return_reason}}",
                        },
                    },
                },
                {
                    "id": "return_confirmed",
                    "type": "llm_response",
                    "position": {"x": 1320, "y": 360},
                    "config": {
                        "instructions": (
                            "Confirm the return has been initiated. "
                            "Let the customer know a prepaid return label will be emailed to them. "
                            "Explain that refund is processed once the item is received."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "escalate",
                    "type": "transfer_human",
                    "position": {"x": 880, "y": 480},
                    "config": {
                        "transfer_number": "+18005550400",
                        "whisper_template": "Order support escalation. Order ID: {{collected.order_id}}, Email: {{collected.email}}.",
                    },
                },
                {
                    "id": "post_action",
                    "type": "post_session_action",
                    "position": {"x": 1540, "y": 220},
                    "config": {"actions": ["send_resolution_email", "update_crm_ticket"]},
                },
                {
                    "id": "end",
                    "type": "end_session",
                    "position": {"x": 1760, "y": 220},
                    "config": {
                        "farewell_message": "Thank you for shopping with us. Is there anything else I can help you with?"
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "greet", "target": "collect_order"},
                {"id": "e2", "source": "collect_order", "target": "issue_type"},
                {"id": "e3", "source": "issue_type", "target": "check_refund_eligibility", "condition": "refund"},
                {"id": "e4", "source": "issue_type", "target": "check_tracking", "condition": "tracking"},
                {"id": "e5", "source": "issue_type", "target": "collect_return_reason", "condition": "return"},
                {"id": "e6", "source": "issue_type", "target": "escalate", "condition": "other"},
                {"id": "e7", "source": "check_refund_eligibility", "target": "refund_eligible"},
                {"id": "e8", "source": "refund_eligible", "target": "process_refund", "condition": "eligible"},
                {"id": "e9", "source": "refund_eligible", "target": "refund_denied", "condition": "ineligible"},
                {"id": "e10", "source": "process_refund", "target": "refund_done"},
                {"id": "e11", "source": "refund_done", "target": "post_action"},
                {"id": "e12", "source": "refund_denied", "target": "post_action"},
                {"id": "e13", "source": "check_tracking", "target": "delivery_status"},
                {"id": "e14", "source": "delivery_status", "target": "post_action"},
                {"id": "e15", "source": "collect_return_reason", "target": "generate_return_label"},
                {"id": "e16", "source": "generate_return_label", "target": "return_confirmed"},
                {"id": "e17", "source": "return_confirmed", "target": "post_action"},
                {"id": "e18", "source": "escalate", "target": "end"},
                {"id": "e19", "source": "post_action", "target": "end"},
            ],
        },
    },

    # ------------------------------------------------------------------
    # 5. Real Estate Inquiry
    # ------------------------------------------------------------------
    {
        "name": "Real Estate Inquiry Agent",
        "language": "en",
        "simple_mode": False,
        "system_prompt": "You are a knowledgeable real estate assistant.",
        "graph_config": {
            "entry_point": "greet",
            "guards": [],
            "nodes": [
                {
                    "id": "greet",
                    "type": "llm_response",
                    "position": {"x": 100, "y": 220},
                    "config": {
                        "instructions": (
                            "Welcome the caller to the real estate agency. "
                            "Ask if they're looking to buy, sell, or rent a property."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "intent",
                    "type": "condition",
                    "position": {"x": 360, "y": 220},
                    "config": {
                        "router_prompt": (
                            "What is the caller's intent?\n"
                            "- buy: Looking to purchase a property\n"
                            "- sell: Looking to sell their property\n"
                            "- rent: Looking to rent a property"
                        ),
                        "routes": [
                            {"label": "buy", "description": "Buyer inquiry"},
                            {"label": "sell", "description": "Seller inquiry"},
                            {"label": "rent", "description": "Rental inquiry"},
                        ],
                    },
                },
                {
                    "id": "collect_buyer_prefs",
                    "type": "collect_data",
                    "position": {"x": 620, "y": 80},
                    "config": {
                        "fields": [
                            {
                                "name": "location",
                                "type": "string",
                                "prompt": "Which city or neighbourhood are you interested in?",
                                "required": True,
                            },
                            {
                                "name": "budget",
                                "type": "string",
                                "prompt": "What is your budget range?",
                                "required": True,
                            },
                            {
                                "name": "property_type",
                                "type": "string",
                                "prompt": "What type of property? (Apartment, Villa, Plot, Commercial)",
                                "required": True,
                            },
                            {
                                "name": "bedrooms",
                                "type": "string",
                                "prompt": "How many bedrooms do you need?",
                                "required": False,
                            },
                            {
                                "name": "timeline",
                                "type": "string",
                                "prompt": "When are you looking to move in?",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "id": "search_listings",
                    "type": "run_tool",
                    "position": {"x": 880, "y": 80},
                    "config": {
                        "tool": "search_property_listings",
                        "input": {
                            "location": "{{collected.location}}",
                            "budget": "{{collected.budget}}",
                            "type": "{{collected.property_type}}",
                            "bedrooms": "{{collected.bedrooms}}",
                        },
                    },
                },
                {
                    "id": "present_listings",
                    "type": "llm_response",
                    "position": {"x": 1100, "y": 80},
                    "config": {
                        "instructions": (
                            "Present the top 3 matching properties to the caller. "
                            "Highlight key features, price, and location for each. "
                            "Ask if any of these interest them or if they'd like to schedule a visit."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "schedule_visit",
                    "type": "collect_data",
                    "position": {"x": 1320, "y": 80},
                    "config": {
                        "fields": [
                            {
                                "name": "visit_date",
                                "type": "string",
                                "prompt": "What date would you like to visit? (e.g. this Saturday, next Monday)",
                                "required": True,
                            },
                            {
                                "name": "contact_name",
                                "type": "string",
                                "prompt": "Your name for the appointment?",
                                "required": True,
                            },
                            {
                                "name": "contact_phone",
                                "type": "string",
                                "prompt": "Best phone number to reach you?",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "id": "book_visit",
                    "type": "http_request",
                    "position": {"x": 1540, "y": 80},
                    "config": {
                        "url": "https://api.example.com/property-visits",
                        "method": "POST",
                        "headers": {"Content-Type": "application/json"},
                        "body": {
                            "name": "{{collected.contact_name}}",
                            "phone": "{{collected.contact_phone}}",
                            "date": "{{collected.visit_date}}",
                            "location": "{{collected.location}}",
                        },
                    },
                },
                {
                    "id": "collect_seller_details",
                    "type": "collect_data",
                    "position": {"x": 620, "y": 260},
                    "config": {
                        "fields": [
                            {
                                "name": "property_address",
                                "type": "string",
                                "prompt": "What is the address of the property you want to sell?",
                                "required": True,
                            },
                            {
                                "name": "property_type",
                                "type": "string",
                                "prompt": "What type of property is it?",
                                "required": True,
                            },
                            {
                                "name": "asking_price",
                                "type": "string",
                                "prompt": "Do you have an asking price in mind?",
                                "required": False,
                            },
                            {
                                "name": "seller_name",
                                "type": "string",
                                "prompt": "Your name?",
                                "required": True,
                            },
                            {
                                "name": "seller_phone",
                                "type": "string",
                                "prompt": "Best number to reach you?",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "id": "get_valuation",
                    "type": "http_request",
                    "position": {"x": 880, "y": 260},
                    "config": {
                        "url": "https://api.example.com/property-valuation",
                        "method": "POST",
                        "headers": {"Content-Type": "application/json"},
                        "body": {
                            "address": "{{collected.property_address}}",
                            "type": "{{collected.property_type}}",
                        },
                    },
                },
                {
                    "id": "seller_handoff",
                    "type": "transfer_human",
                    "position": {"x": 1100, "y": 260},
                    "config": {
                        "transfer_number": "+18005550500",
                        "whisper_template": (
                            "Seller lead: {{collected.seller_name}}, property at {{collected.property_address}}, "
                            "type {{collected.property_type}}, asking {{collected.asking_price}}."
                        ),
                    },
                },
                {
                    "id": "collect_renter_prefs",
                    "type": "collect_data",
                    "position": {"x": 620, "y": 420},
                    "config": {
                        "fields": [
                            {
                                "name": "location",
                                "type": "string",
                                "prompt": "Which area are you looking to rent in?",
                                "required": True,
                            },
                            {
                                "name": "budget",
                                "type": "string",
                                "prompt": "What is your monthly rent budget?",
                                "required": True,
                            },
                            {
                                "name": "move_in_date",
                                "type": "string",
                                "prompt": "When do you need to move in?",
                                "required": True,
                            },
                            {
                                "name": "renter_name",
                                "type": "string",
                                "prompt": "Your name?",
                                "required": True,
                            },
                            {
                                "name": "renter_phone",
                                "type": "string",
                                "prompt": "Your phone number?",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "id": "renter_handoff",
                    "type": "transfer_human",
                    "position": {"x": 880, "y": 420},
                    "config": {
                        "transfer_number": "+18005550500",
                        "whisper_template": "Rental inquiry: {{collected.renter_name}}, area {{collected.location}}, budget {{collected.budget}}, move-in {{collected.move_in_date}}.",
                    },
                },
                {
                    "id": "post_action",
                    "type": "post_session_action",
                    "position": {"x": 1540, "y": 260},
                    "config": {"actions": ["create_crm_lead", "send_property_brochure"]},
                },
                {
                    "id": "end",
                    "type": "end_session",
                    "position": {"x": 1760, "y": 220},
                    "config": {
                        "farewell_message": "Thank you for your interest! Our team will be in touch shortly."
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "greet", "target": "intent"},
                {"id": "e2", "source": "intent", "target": "collect_buyer_prefs", "condition": "buy"},
                {"id": "e3", "source": "intent", "target": "collect_seller_details", "condition": "sell"},
                {"id": "e4", "source": "intent", "target": "collect_renter_prefs", "condition": "rent"},
                {"id": "e5", "source": "collect_buyer_prefs", "target": "search_listings"},
                {"id": "e6", "source": "search_listings", "target": "present_listings"},
                {"id": "e7", "source": "present_listings", "target": "schedule_visit"},
                {"id": "e8", "source": "schedule_visit", "target": "book_visit"},
                {"id": "e9", "source": "book_visit", "target": "post_action"},
                {"id": "e10", "source": "collect_seller_details", "target": "get_valuation"},
                {"id": "e11", "source": "get_valuation", "target": "seller_handoff"},
                {"id": "e12", "source": "seller_handoff", "target": "post_action"},
                {"id": "e13", "source": "collect_renter_prefs", "target": "renter_handoff"},
                {"id": "e14", "source": "renter_handoff", "target": "post_action"},
                {"id": "e15", "source": "post_action", "target": "end"},
            ],
        },
    },

    # ------------------------------------------------------------------
    # 6. HR Onboarding & FAQ
    # ------------------------------------------------------------------
    {
        "name": "HR Onboarding Agent",
        "language": "en",
        "simple_mode": False,
        "system_prompt": "You are a helpful HR onboarding assistant.",
        "graph_config": {
            "entry_point": "greet",
            "guards": [],
            "nodes": [
                {
                    "id": "greet",
                    "type": "llm_response",
                    "position": {"x": 100, "y": 220},
                    "config": {
                        "instructions": (
                            "Welcome the employee warmly. Let them know you can help with HR policies, "
                            "onboarding paperwork, benefits questions, or connect them with an HR specialist. "
                            "Ask how you can help today."
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "route_query",
                    "type": "condition",
                    "position": {"x": 380, "y": 220},
                    "config": {
                        "router_prompt": (
                            "What type of query is this?\n"
                            "- policy: Questions about company policies (PTO, benefits, dress code, WFH)\n"
                            "- onboarding: New hire completing onboarding steps or paperwork\n"
                            "- complex: Sensitive issues, disputes, visa/relocation, payroll errors"
                        ),
                        "routes": [
                            {"label": "policy", "description": "Policy or FAQ question"},
                            {"label": "onboarding", "description": "New hire onboarding"},
                            {"label": "complex", "description": "Needs HR specialist"},
                        ],
                    },
                },
                {
                    "id": "policy_lookup",
                    "type": "rag_search",
                    "position": {"x": 660, "y": 80},
                    "config": {
                        "query_template": "{{collected.query}} company policy"
                    },
                },
                {
                    "id": "policy_answer",
                    "type": "llm_response",
                    "position": {"x": 900, "y": 80},
                    "config": {
                        "instructions": (
                            "Answer the employee's policy question using the knowledge base. "
                            "Be clear and cite the relevant policy section. "
                            "Ask if they need clarification or have other questions."
                        ),
                        "rag_enabled": True,
                        "tools": [],
                    },
                },
                {
                    "id": "collect_employee_info",
                    "type": "collect_data",
                    "position": {"x": 660, "y": 220},
                    "config": {
                        "fields": [
                            {
                                "name": "full_name",
                                "type": "string",
                                "prompt": "Welcome! What is your full name?",
                                "required": True,
                            },
                            {
                                "name": "work_email",
                                "type": "string",
                                "prompt": "What is your work email address?",
                                "required": True,
                            },
                            {
                                "name": "start_date",
                                "type": "string",
                                "prompt": "What is your start date?",
                                "required": True,
                            },
                            {
                                "name": "department",
                                "type": "string",
                                "prompt": "Which department are you joining?",
                                "required": True,
                            },
                            {
                                "name": "manager_name",
                                "type": "string",
                                "prompt": "Who is your reporting manager?",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "id": "collect_benefits",
                    "type": "collect_data",
                    "position": {"x": 900, "y": 220},
                    "config": {
                        "fields": [
                            {
                                "name": "health_plan",
                                "type": "string",
                                "prompt": "Which health insurance plan would you like? (Basic, Standard, Premium)",
                                "required": True,
                            },
                            {
                                "name": "pf_contribution",
                                "type": "string",
                                "prompt": "What percentage would you like to contribute to PF beyond statutory minimum? (0%, 5%, 10%, 12%)",
                                "required": True,
                            },
                            {
                                "name": "emergency_contact",
                                "type": "string",
                                "prompt": "Emergency contact name and phone number?",
                                "required": True,
                            },
                        ]
                    },
                },
                {
                    "id": "create_employee_record",
                    "type": "run_tool",
                    "position": {"x": 1120, "y": 220},
                    "config": {
                        "tool": "create_employee_record",
                        "input": {
                            "name": "{{collected.full_name}}",
                            "email": "{{collected.work_email}}",
                            "start_date": "{{collected.start_date}}",
                            "department": "{{collected.department}}",
                            "manager": "{{collected.manager_name}}",
                            "health_plan": "{{collected.health_plan}}",
                        },
                    },
                },
                {
                    "id": "onboarding_done",
                    "type": "llm_response",
                    "position": {"x": 1340, "y": 220},
                    "config": {
                        "instructions": (
                            "Congratulate the new employee on completing their onboarding. "
                            "Let them know:\n"
                            "1. IT will email laptop setup instructions within 24 hours\n"
                            "2. Benefits portal access will be emailed separately\n"
                            "3. Their manager {{collected.manager_name}} will reach out before their first day\n"
                            "Wish them well!"
                        ),
                        "rag_enabled": False,
                        "tools": [],
                    },
                },
                {
                    "id": "post_onboarding",
                    "type": "post_session_action",
                    "position": {"x": 1340, "y": 360},
                    "config": {
                        "actions": [
                            "send_welcome_email",
                            "create_it_ticket",
                            "notify_manager",
                            "enroll_benefits",
                        ]
                    },
                },
                {
                    "id": "hr_specialist",
                    "type": "transfer_human",
                    "position": {"x": 660, "y": 380},
                    "config": {
                        "transfer_number": "+18005550600",
                        "whisper_template": "HR escalation from employee. Issue requires specialist attention.",
                    },
                },
                {
                    "id": "end",
                    "type": "end_session",
                    "position": {"x": 1560, "y": 220},
                    "config": {
                        "farewell_message": "Thank you! Don't hesitate to reach out if you need anything else. Welcome to the team!"
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "greet", "target": "route_query"},
                {"id": "e2", "source": "route_query", "target": "policy_lookup", "condition": "policy"},
                {"id": "e3", "source": "route_query", "target": "collect_employee_info", "condition": "onboarding"},
                {"id": "e4", "source": "route_query", "target": "hr_specialist", "condition": "complex"},
                {"id": "e5", "source": "policy_lookup", "target": "policy_answer"},
                {"id": "e6", "source": "policy_answer", "target": "end"},
                {"id": "e7", "source": "collect_employee_info", "target": "collect_benefits"},
                {"id": "e8", "source": "collect_benefits", "target": "create_employee_record"},
                {"id": "e9", "source": "create_employee_record", "target": "onboarding_done"},
                {"id": "e10", "source": "onboarding_done", "target": "post_onboarding"},
                {"id": "e11", "source": "post_onboarding", "target": "end"},
                {"id": "e12", "source": "hr_specialist", "target": "end"},
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------

async def seed(org_id: str) -> None:
    async with async_session_factory() as db:
        from sqlalchemy import select

        # Check how many already seeded (by name match)
        existing_names_result = await db.execute(
            select(Agent.name).where(
                Agent.org_id == org_id,
                Agent.deleted_at.is_(None),
            )
        )
        existing_names = {row[0] for row in existing_names_result.all()}

        created = 0
        skipped = 0
        for agent_def in AGENTS:
            if agent_def["name"] in existing_names:
                print(f"  skip  {agent_def['name']} (already exists)")
                skipped += 1
                continue

            agent = Agent(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name=agent_def["name"],
                language=agent_def["language"],
                system_prompt=agent_def["system_prompt"],
                simple_mode=agent_def["simple_mode"],
                graph_config=agent_def["graph_config"],
            )
            db.add(agent)
            print(f"  create {agent_def['name']}")
            created += 1

        await db.commit()
        print(f"\nDone — {created} created, {skipped} skipped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed default agents for testing.")
    parser.add_argument("--org-id", required=True, help="Organization ID to seed agents into")
    args = parser.parse_args()

    asyncio.run(seed(args.org_id))


if __name__ == "__main__":
    main()
