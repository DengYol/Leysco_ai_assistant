"""
app/ai_engine/training_actions.py
=================================
Complete Training Module for Leysco100
Based on actual system modules and sub-modules
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TrainingActions:
    """
    Handles training and onboarding for all Leysco100 modules.
    Based on actual system structure from screenshots.
    """

    def __init__(self):
        self.training_modules = {
            # =========================================================
            # 1. ADMINISTRATION MODULE - Complete System Setup
            # =========================================================
            "administration": {
                "id": "administration",
                "title": "⚙️ System Administration",
                "description": "Complete system configuration, user management, and global settings",
                "sub_modules": {
                    "rates_and_indexes": {
                        "title": "💰 Rates and Indexes",
                        "steps": [
                            "1️⃣ Administration → Rates and Indexes",
                            "2️⃣ Select currency or index to update",
                            "3️⃣ Enter new exchange rate or index value",
                            "4️⃣ Set effective date for the rate",
                            "5️⃣ Add source reference if available",
                            "6️⃣ Save and verify updates in transactions"
                        ],
                        "tips": [
                            "💡 Update rates daily for accurate conversions",
                            "💡 Set up automatic rate feeds if available",
                            "💡 Maintain historical rates for reporting"
                        ]
                    },
                    "ip_restrictions": {
                        "title": "🔒 IP Restrictions",
                        "steps": [
                            "1️⃣ Administration → IP Restrictions",
                            "2️⃣ Add new IP address or range",
                            "3️⃣ Assign to specific users or user groups",
                            "4️⃣ Set access level (Full/Read-only/None)",
                            "5️⃣ Configure allowed time windows",
                            "6️⃣ Test restrictions before enforcing"
                        ],
                        "tips": [
                            "💡 Use for remote workers with fixed IPs",
                            "💡 Set up office IP ranges for internal access",
                            "💡 Monitor blocked access attempts"
                        ]
                    },
                    "system_initialization": {
                        "title": "🚀 System Initialization",
                        "sub_modules": {
                            "company_details": {
                                "title": "🏢 Company Details",
                                "steps": [
                                    "1️⃣ Administration → System Initialization → Company Details",
                                    "2️⃣ Enter company legal name and trading name",
                                    "3️⃣ Add registration numbers (PIN, VAT, etc.)",
                                    "4️⃣ Set company address and contact information",
                                    "5️⃣ Configure fiscal year start date",
                                    "6️⃣ Upload company logo for documents"
                                ],
                                "tips": [
                                    "💡 Verify all details match legal documents",
                                    "💡 Set up multiple branches if applicable",
                                    "💡 Keep contact information updated"
                                ]
                            },
                            "general_settings": {
                                "title": "⚙️ General Settings",
                                "steps": [
                                    "1️⃣ Administration → System Initialization → General Settings",
                                    "2️⃣ Set system date format and separator",
                                    "3️⃣ Configure decimal places for quantities/prices",
                                    "4️⃣ Choose default currency",
                                    "5️⃣ Set session timeout duration",
                                    "6️⃣ Configure email server settings"
                                ],
                                "tips": [
                                    "💡 Match date format to regional standards",
                                    "💡 Set reasonable session timeouts for security",
                                    "💡 Test email settings with test message"
                                ]
                            },
                            "document_numbering": {
                                "title": "🔢 Document Numbering",
                                "steps": [
                                    "1️⃣ Administration → System Initialization → Document Numbering",
                                    "2️⃣ Select document type (Quotation, Order, Invoice, etc.)",
                                    "3️⃣ Define numbering series format",
                                    "4️⃣ Set starting number and prefix/suffix",
                                    "5️⃣ Configure manual or automatic numbering",
                                    "6️⃣ Test numbering with sample document"
                                ],
                                "tips": [
                                    "💡 Use prefixes to identify document types",
                                    "💡 Create separate series for each branch",
                                    "💡 Avoid gaps in numbering for audit purposes"
                                ]
                            },
                            "posting_periods": {
                                "title": "📅 Posting Periods",
                                "steps": [
                                    "1️⃣ Administration → System Initialization → Posting Periods",
                                    "2️⃣ Define fiscal year periods (monthly/quarterly)",
                                    "3️⃣ Set period opening and closing dates",
                                    "4️⃣ Configure period status (Open/Closed)",
                                    "5️⃣ Set up period indicators for reporting",
                                    "6️⃣ Lock closed periods to prevent changes"
                                ],
                                "tips": [
                                    "💡 Close periods monthly for accurate reporting",
                                    "💡 Keep current period open for transactions",
                                    "💡 Plan year-end closing procedures"
                                ]
                            },
                            "document_approvals": {
                                "title": "✓ Document Approvals",
                                "steps": [
                                    "1️⃣ Administration → System Initialization → Document Approvals",
                                    "2️⃣ Enable approval workflow for document types",
                                    "3️⃣ Define approval stages and hierarchy",
                                    "4️⃣ Set approval thresholds by amount",
                                    "5️⃣ Assign approvers to stages",
                                    "6️⃣ Configure email notifications"
                                ],
                                "tips": [
                                    "💡 Set up different approval paths by department",
                                    "💡 Allow delegation for approver absence",
                                    "💡 Monitor pending approvals regularly"
                                ]
                            },
                            "form_settings": {
                                "title": "📋 Form Settings",
                                "steps": [
                                    "1️⃣ Administration → System Initialization → Form Settings",
                                    "2️⃣ Customize form layouts for each document type",
                                    "3️⃣ Choose which fields are visible/mandatory",
                                    "4️⃣ Set default values for fields",
                                    "5️⃣ Configure form behavior (auto-refresh, etc.)",
                                    "6️⃣ Save templates for different user roles"
                                ],
                                "tips": [
                                    "💡 Simplify forms for data entry users",
                                    "💡 Show all fields for power users",
                                    "💡 Test changes before rolling out"
                                ]
                            }
                        }
                    },
                    "authorizations": {
                        "title": "🔐 Authorizations",
                        "sub_modules": {
                            "general_authorization": {
                                "title": "👥 General Authorization",
                                "steps": [
                                    "1️⃣ Administration → Authorizations → General Authorization",
                                    "2️⃣ Create authorization groups (Sales, Finance, Warehouse)",
                                    "3️⃣ Assign users to groups",
                                    "4️⃣ Set module-level permissions (Read/Write/None)",
                                    "5️⃣ Configure document type permissions",
                                    "6️⃣ Set report access rights"
                                ],
                                "tips": [
                                    "💡 Follow principle of least privilege",
                                    "💡 Review permissions quarterly",
                                    "💡 Create templates for common roles"
                                ]
                            },
                            "data_ownerships": {
                                "title": "📊 Data Ownerships",
                                "steps": [
                                    "1️⃣ Administration → Authorizations → Data Ownerships",
                                    "2️⃣ Define ownership rules by branch/department",
                                    "3️⃣ Set up data visibility restrictions",
                                    "4️⃣ Configure sales employee territories",
                                    "5️⃣ Assign document ownership automatically",
                                    "6️⃣ Test with sample users"
                                ],
                                "tips": [
                                    "💡 Use for multi-branch organizations",
                                    "💡 Prevent cross-branch data access",
                                    "💡 Allow managers to see all data"
                                ]
                            }
                        }
                    },
                    "setup": {
                        "title": "🔧 Setup",
                        "sub_modules": {
                            "users": {
                                "title": "👤 Users",
                                "steps": [
                                    "1️⃣ Administration → Setup → Users",
                                    "2️⃣ Click 'Add New User'",
                                    "3️⃣ Enter user details (name, email, employee ID)",
                                    "4️⃣ Set login credentials and password policies",
                                    "5️⃣ Assign user groups and authorizations",
                                    "6️⃣ Configure user defaults (branch, printer)"
                                ],
                                "tips": [
                                    "💡 Use employee IDs for consistency",
                                    "💡 Set password expiry for security",
                                    "💡 Disable accounts for departed employees"
                                ]
                            },
                            "departments": {
                                "title": "🏢 Departments",
                                "steps": [
                                    "1️⃣ Administration → Setup → Departments",
                                    "2️⃣ Add department code and name",
                                    "3️⃣ Assign department head",
                                    "4️⃣ Set cost center if applicable",
                                    "5️⃣ Link to branches",
                                    "6️⃣ Define reporting hierarchy"
                                ],
                                "tips": [
                                    "💡 Align with organizational structure",
                                    "💡 Use for cost allocation",
                                    "💡 Track expenses by department"
                                ]
                            },
                            "user_groups": {
                                "title": "👥 User Groups",
                                "steps": [
                                    "1️⃣ Administration → Setup → User Groups",
                                    "2️⃣ Create group names (Managers, Clerks, Viewers)",
                                    "3️⃣ Assign authorization templates",
                                    "4️⃣ Add users to groups",
                                    "5️⃣ Set group-specific defaults",
                                    "6️⃣ Review group memberships regularly"
                                ],
                                "tips": [
                                    "💡 Manage permissions at group level",
                                    "💡 Create groups by function",
                                    "💡 Simplify onboarding with group assignments"
                                ]
                            },
                            "sales_employees": {
                                "title": "💼 Sales Employees",
                                "steps": [
                                    "1️⃣ Administration → Setup → Sales Employees",
                                    "2️⃣ Add sales rep code and name",
                                    "3️⃣ Link to user account",
                                    "4️⃣ Assign commission rates",
                                    "5️⃣ Set sales targets",
                                    "6️⃣ Define territory coverage"
                                ],
                                "tips": [
                                    "💡 Track performance by sales rep",
                                    "💡 Calculate commissions automatically",
                                    "💡 Set realistic targets"
                                ]
                            },
                            "employees": {
                                "title": "👔 Employees",
                                "steps": [
                                    "1️⃣ Administration → Setup → Employees",
                                    "2️⃣ Enter employee personal details",
                                    "3️⃣ Set employment details (hire date, position)",
                                    "4️⃣ Assign department and manager",
                                    "5️⃣ Add emergency contacts",
                                    "6️⃣ Upload employment documents"
                                ],
                                "tips": [
                                    "💡 Keep employee records confidential",
                                    "💡 Update status on termination",
                                    "💡 Link to user accounts"
                                ]
                            },
                            "drivers": {
                                "title": "🚛 Drivers",
                                "steps": [
                                    "1️⃣ Administration → Setup → Drivers",
                                    "2️⃣ Add driver name and code",
                                    "3️⃣ Enter license details and expiry",
                                    "4️⃣ Assign vehicle(s)",
                                    "5️⃣ Set contact information",
                                    "6️⃣ Track training and certifications"
                                ],
                                "tips": [
                                    "💡 Monitor license renewals",
                                    "💡 Link to deliveries for tracking",
                                    "💡 Keep emergency contacts"
                                ]
                            },
                            "territories": {
                                "title": "🗺️ Territories",
                                "steps": [
                                    "1️⃣ Administration → Setup → Territories",
                                    "2️⃣ Define territory boundaries",
                                    "3️⃣ Assign to sales employees",
                                    "4️⃣ Set up territory hierarchies",
                                    "5️⃣ Link to customers",
                                    "6️⃣ Track sales by territory"
                                ],
                                "tips": [
                                    "💡 Balance territory workloads",
                                    "💡 Analyze performance by region",
                                    "💡 Adjust territories as business grows"
                                ]
                            },
                            "commission_groups": {
                                "title": "💰 Commission Groups",
                                "steps": [
                                    "1️⃣ Administration → Setup → Commission Groups",
                                    "2️⃣ Create commission tiers",
                                    "3️⃣ Set percentage rates by product/category",
                                    "4️⃣ Define calculation basis (revenue, profit)",
                                    "5️⃣ Assign to sales employees",
                                    "6️⃣ Test commission calculations"
                                ],
                                "tips": [
                                    "💡 Incentivize high-margin products",
                                    "💡 Review commission structures annually",
                                    "💡 Handle team commissions fairly"
                                ]
                            },
                            "user_defaults": {
                                "title": "⚙️ User Defaults",
                                "steps": [
                                    "1️⃣ Administration → Setup → User Defaults",
                                    "2️⃣ Set default branch for each user",
                                    "3️⃣ Configure default printer",
                                    "4️⃣ Set default warehouse",
                                    "5️⃣ Define default price list",
                                    "6️⃣ Set dashboard preferences"
                                ],
                                "tips": [
                                    "💡 Save time with personalized defaults",
                                    "💡 Allow users to customize",
                                    "💡 Reset to company standards if needed"
                                ]
                            },
                            "branches": {
                                "title": "🏬 Branches",
                                "steps": [
                                    "1️⃣ Administration → Setup → Branches",
                                    "2️⃣ Add branch code and name",
                                    "3️⃣ Enter branch address and contacts",
                                    "4️⃣ Assign branch manager",
                                    "5️⃣ Set up inter-branch transfers",
                                    "6️⃣ Track branch profitability"
                                ],
                                "tips": [
                                    "💡 Treat branches as profit centers",
                                    "💡 Enable inter-branch visibility as needed",
                                    "💡 Consolidate reports at HQ"
                                ]
                            },
                            "freight": {
                                "title": "📦 Freight",
                                "steps": [
                                    "1️⃣ Administration → Setup → Freight",
                                    "2️⃣ Define freight carriers",
                                    "3️⃣ Set up shipping zones",
                                    "4️⃣ Configure freight rates by weight/distance",
                                    "5️⃣ Link to delivery documents",
                                    "6️⃣ Track freight costs"
                                ],
                                "tips": [
                                    "💡 Negotiate rates with carriers",
                                    "💡 Pass through costs to customers",
                                    "💡 Analyze freight efficiency"
                                ]
                            },
                            "locations": {
                                "title": "📍 Locations",
                                "steps": [
                                    "1️⃣ Administration → Setup → Locations",
                                    "2️⃣ Define location types (Office, Warehouse, Store)",
                                    "3️⃣ Add location codes and names",
                                    "4️⃣ Enter GPS coordinates",
                                    "5️⃣ Assign operating hours",
                                    "6️⃣ Link to employees and assets"
                                ],
                                "tips": [
                                    "💡 Use for route planning",
                                    "💡 Track assets by location",
                                    "💡 Optimize logistics"
                                ]
                            },
                            "vehicles": {
                                "title": "🚗 Vehicles",
                                "steps": [
                                    "1️⃣ Administration → Setup → Vehicles",
                                    "2️⃣ Add vehicle registration and details",
                                    "3️⃣ Record insurance and maintenance info",
                                    "4️⃣ Assign to drivers",
                                    "5️⃣ Track fuel consumption",
                                    "6️⃣ Schedule service reminders"
                                ],
                                "tips": [
                                    "💡 Monitor vehicle operating costs",
                                    "💡 Schedule preventive maintenance",
                                    "💡 Track utilization rates"
                                ]
                            },
                            "timesheets": {
                                "title": "⏱️ Timesheets",
                                "steps": [
                                    "1️⃣ Administration → Setup → Timesheets",
                                    "2️⃣ Configure timesheet templates",
                                    "3️⃣ Set up approval workflow",
                                    "4️⃣ Link to projects or activities",
                                    "5️⃣ Track employee hours",
                                    "6️⃣ Generate payroll reports"
                                ],
                                "tips": [
                                    "💡 Use for project costing",
                                    "💡 Track overtime for compliance",
                                    "💡 Integrate with payroll"
                                ]
                            }
                        }
                    },
                    "security": {
                        "title": "🛡️ Security",
                        "sub_modules": {
                            "password_administration": {
                                "title": "🔑 Password Administration",
                                "steps": [
                                    "1️⃣ Administration → Security → Password Administration",
                                    "2️⃣ Set password complexity requirements",
                                    "3️⃣ Configure password expiry period",
                                    "4️⃣ Set failed login attempt limits",
                                    "5️⃣ Enable two-factor authentication",
                                    "6️⃣ Review password audit logs"
                                ],
                                "tips": [
                                    "💡 Enforce strong passwords",
                                    "💡 Educate users on security",
                                    "💡 Lock accounts after multiple failures"
                                ]
                            }
                        }
                    },
                    "license_administration": {
                        "title": "📄 License Administration",
                        "steps": [
                            "1️⃣ Administration → License Administration",
                            "2️⃣ View current license status",
                            "3️⃣ Check user count and limits",
                            "4️⃣ Add or remove licenses as needed",
                            "5️⃣ Review expiration dates",
                            "6️⃣ Renew before expiration"
                        ],
                        "tips": [
                            "💡 Monitor license usage",
                            "💡 Plan for growth",
                            "💡 Renew before expiration to avoid disruption"
                        ]
                    },
                    "create_surveys": {
                        "title": "📝 Create Surveys",
                        "steps": [
                            "1️⃣ Administration → Create Surveys",
                            "2️⃣ Define survey title and purpose",
                            "3️⃣ Add questions (multiple choice, text, rating)",
                            "4️⃣ Set target audience",
                            "5️⃣ Configure distribution method",
                            "6️⃣ Analyze responses"
                        ],
                        "tips": [
                            "💡 Use for customer feedback",
                            "💡 Keep surveys short",
                            "💡 Incentivize participation"
                        ]
                    },
                    "alerts_management": {
                        "title": "🔔 Alerts Management",
                        "steps": [
                            "1️⃣ Administration → Alerts Management",
                            "2️⃣ Create new alert definition",
                            "3️⃣ Set trigger conditions",
                            "4️⃣ Choose notification method (email, SMS, popup)",
                            "5️⃣ Select recipients",
                            "6️⃣ Test and activate alert"
                        ],
                        "tips": [
                            "💡 Set low stock alerts",
                            "💡 Monitor credit limit exceedances",
                            "💡 Avoid alert fatigue - focus on critical"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/administration",
                "doc_url": "https://docs.leysco.com/admin-guide",
                "estimated_time": "45 minutes",
                "prerequisites": ["System administrator access"],
                "keywords": ["admin", "users", "permissions", "settings", "security", "setup"]
            },

            # =========================================================
            # 2. FINANCIALS MODULE - Accounting Master Data
            # =========================================================
            "financials": {
                "id": "financials",
                "title": "💰 Financials Master Data",
                "description": "Configure all financial master data including chart of accounts, currencies, and tax groups",
                "sub_modules": {
                    "edit_chart_of_accounts": {
                        "title": "📊 Edit Chart of Accounts",
                        "steps": [
                            "1️⃣ Financials → Edit Chart of Accounts",
                            "2️⃣ Create new account with code and name",
                            "3️⃣ Select account type (Asset, Liability, Equity, Revenue, Expense)",
                            "4️⃣ Assign account group and category",
                            "5️⃣ Set control accounts (Cash, AR, AP)",
                            "6️⃣ Define foreign currency accounts if needed"
                        ],
                        "tips": [
                            "💡 Use logical account numbering (1000-1999 Assets)",
                            "💡 Create account groups for reporting",
                            "💡 Plan for future expansion"
                        ]
                    },
                    "gl_account_determination": {
                        "title": "🔍 G/L Account Determination",
                        "steps": [
                            "1️⃣ Financials → G/L Account Determination",
                            "2️⃣ Map transaction types to G/L accounts",
                            "3️⃣ Set up default accounts for sales, purchases",
                            "4️⃣ Configure tax accounts",
                            "5️⃣ Define inventory posting accounts",
                            "6️⃣ Test with sample transactions"
                        ],
                        "tips": [
                            "💡 Ensure all transaction types are mapped",
                            "💡 Review periodically for accuracy",
                            "💡 Document mapping for audit trail"
                        ]
                    },
                    "currencies": {
                        "title": "💱 Currencies",
                        "steps": [
                            "1️⃣ Financials → Currencies",
                            "2️⃣ Add new currency code and symbol",
                            "3️⃣ Set decimal places",
                            "4️⃣ Define rounding rules",
                            "5️⃣ Link to exchange rate sources",
                            "6️⃣ Set as default if applicable"
                        ],
                        "tips": [
                            "💡 Include all currencies you transact in",
                            "💡 Update exchange rates regularly",
                            "💡 Handle multi-currency carefully"
                        ]
                    },
                    "tax_groups": {
                        "title": "🧾 Tax Groups",
                        "steps": [
                            "1️⃣ Financials → Tax Groups",
                            "2️⃣ Create tax group (VAT, Sales Tax, Withholding)",
                            "3️⃣ Set tax rate percentage",
                            "4️⃣ Define effective dates",
                            "5️⃣ Link to G/L accounts",
                            "6️⃣ Apply to customers/suppliers"
                        ],
                        "tips": [
                            "💡 Stay compliant with tax regulations",
                            "💡 Update rates when laws change",
                            "💡 Test tax calculations"
                        ]
                    },
                    "business_partners_fin": {
                        "title": "👥 Business Partners (Financial)",
                        "steps": [
                            "1️⃣ Financials → Business Partners",
                            "2️⃣ Link customers to tax groups",
                            "3️⃣ Set payment terms",
                            "4️⃣ Define credit limits",
                            "5️⃣ Configure price lists",
                            "6️⃣ Set up partner-specific GL accounts"
                        ],
                        "tips": [
                            "💡 Review credit limits regularly",
                            "💡 Enforce payment terms",
                            "💡 Segment partners for reporting"
                        ]
                    },
                    "countries": {
                        "title": "🌍 Countries",
                        "steps": [
                            "1️⃣ Financials → Countries",
                            "2️⃣ Add country code and name",
                            "3️⃣ Set region (Africa, Europe, etc.)",
                            "4️⃣ Configure tax rules per country",
                            "5️⃣ Set currency for country",
                            "6️⃣ Add address format template"
                        ],
                        "tips": [
                            "💡 Include all countries you do business with",
                            "💡 Understand local tax requirements",
                            "💡 Format addresses correctly for shipping"
                        ]
                    },
                    "customer_groups": {
                        "title": "👥 Customer Groups",
                        "steps": [
                            "1️⃣ Financials → Customer Groups",
                            "2️⃣ Create groups (Retail, Wholesale, Distributor)",
                            "3️⃣ Assign default price lists",
                            "4️⃣ Set discount percentages",
                            "5️⃣ Define payment terms by group",
                            "6️⃣ Analyze profitability by group"
                        ],
                        "tips": [
                            "💡 Segment for targeted marketing",
                            "💡 Offer group-specific promotions",
                            "💡 Track group performance"
                        ]
                    },
                    "properties": {
                        "title": "🏷️ Properties",
                        "steps": [
                            "1️⃣ Financials → Properties",
                            "2️⃣ Define custom fields for master data",
                            "3️⃣ Set data types (text, number, date)",
                            "4️⃣ Make fields mandatory if needed",
                            "5️⃣ Use in reporting and segmentation",
                            "6️⃣ Apply to customers, items, vendors"
                        ],
                        "tips": [
                            "💡 Use for industry-specific attributes",
                            "💡 Keep properties organized",
                            "💡 Document custom fields"
                        ]
                    },
                    "payment_terms": {
                        "title": "📅 Payment Terms",
                        "steps": [
                            "1️⃣ Financials → Payment Terms",
                            "2️⃣ Create term (Net 30, 2/10 Net 30, etc.)",
                            "3️⃣ Set due date calculation",
                            "4️⃣ Define discount percentage and period",
                            "5️⃣ Apply to customers/vendors",
                            "6️⃣ Track payment compliance"
                        ],
                        "tips": [
                            "💡 Encourage early payment with discounts",
                            "💡 Enforce terms consistently",
                            "💡 Monitor aging by term"
                        ]
                    },
                    "address_formats": {
                        "title": "📮 Address Formats",
                        "steps": [
                            "1️⃣ Financials → Address Formats",
                            "2️⃣ Create format templates by country",
                            "3️⃣ Define field order (Street, City, Postal Code)",
                            "4️⃣ Set required fields",
                            "5️⃣ Apply to business partners",
                            "6️⃣ Test with shipping labels"
                        ],
                        "tips": [
                            "💡 Ensure compatibility with courier systems",
                            "💡 Include local addressing conventions",
                            "💡 Validate addresses before shipping"
                        ]
                    },
                    "branch_defaults": {
                        "title": "🏢 Branch Defaults",
                        "steps": [
                            "1️⃣ Financials → Branch Defaults",
                            "2️⃣ Set default G/L accounts per branch",
                            "3️⃣ Configure branch-specific tax rules",
                            "4️⃣ Define inventory valuation by branch",
                            "5️⃣ Set up inter-branch transfer accounts",
                            "6️⃣ Track branch profitability"
                        ],
                        "tips": [
                            "💡 Treat branches as separate entities",
                            "💡 Consolidate for corporate reporting",
                            "💡 Monitor branch performance"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/financials",
                "doc_url": "https://docs.leysco.com/financials-guide",
                "estimated_time": "35 minutes",
                "prerequisites": ["Finance access rights", "Accounting knowledge"],
                "keywords": ["finance", "chart of accounts", "tax", "currency", "gl"]
            },

            # =========================================================
            # 3. BANKING MODULE - Bank Master Data
            # =========================================================
            "banking_master": {
                "id": "banking_master",
                "title": "💳 Banking Master Data",
                "description": "Configure bank accounts and banking master data",
                "sub_modules": {
                    "banks": {
                        "title": "🏦 Banks",
                        "steps": [
                            "1️⃣ Banking → Banks",
                            "2️⃣ Add bank name and code",
                            "3️⃣ Enter bank contact information",
                            "4️⃣ Set up bank branches",
                            "5️⃣ Configure bank statement formats",
                            "6️⃣ Link to house bank accounts"
                        ],
                        "tips": [
                            "💡 Include all banks you work with",
                            "💡 Keep contact details updated",
                            "💡 Understand bank file formats"
                        ]
                    },
                    "house_bank_accounts": {
                        "title": "🏧 House Bank Accounts",
                        "steps": [
                            "1️⃣ Banking → House Bank Accounts",
                            "2️⃣ Add account number and name",
                            "3️⃣ Select bank and currency",
                            "4️⃣ Set up GL account linkage",
                            "5️⃣ Configure check printing templates",
                            "6️⃣ Set opening balance"
                        ],
                        "tips": [
                            "💡 Maintain separate accounts per currency",
                            "💡 Reconcile accounts regularly",
                            "💡 Secure check stock"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/banking",
                "doc_url": "https://docs.leysco.com/banking-guide",
                "estimated_time": "15 minutes",
                "prerequisites": ["Finance access rights"],
                "keywords": ["bank", "account", "check", "reconciliation"]
            },

            # =========================================================
            # 4. INVENTORY MASTER DATA
            # =========================================================
            "inventory_master": {
                "id": "inventory_master",
                "title": "📦 Inventory Master Data",
                "description": "Configure all inventory-related master data",
                "sub_modules": {
                    "item_groups": {
                        "title": "📋 Item Groups",
                        "steps": [
                            "1️⃣ Inventory → Item Groups",
                            "2️⃣ Create group (Fertilizers, Seeds, Chemicals)",
                            "3️⃣ Assign default UoM",
                            "4️⃣ Set default price lists",
                            "5️⃣ Define group-level discounts",
                            "6️⃣ Link to G/L accounts"
                        ],
                        "tips": [
                            "💡 Organize items logically",
                            "💡 Use groups for reporting",
                            "💡 Apply group-level pricing"
                        ]
                    },
                    "item_properties": {
                        "title": "🏷️ Item Properties",
                        "steps": [
                            "1️⃣ Inventory → Item Properties",
                            "2️⃣ Define custom attributes",
                            "3️⃣ Set data types (text, number, date)",
                            "4️⃣ Apply to item categories",
                            "5️⃣ Use in search and reporting",
                            "6️⃣ Track specifications"
                        ],
                        "tips": [
                            "💡 Capture all relevant item details",
                            "💡 Use for certification tracking",
                            "💡 Enable better search"
                        ]
                    },
                    "warehouses": {
                        "title": "🏭 Warehouses",
                        "steps": [
                            "1️⃣ Inventory → Warehouses",
                            "2️⃣ Add warehouse code and name",
                            "3️⃣ Enter location address",
                            "4️⃣ Set warehouse type (Main, Transit, Returns)",
                            "5️⃣ Assign warehouse manager",
                            "6️⃣ Configure bin locations"
                        ],
                        "tips": [
                            "💡 Set up logical warehouse structure",
                            "💡 Use for multi-location inventory",
                            "💡 Track by warehouse profitability"
                        ]
                    },
                    "warehouse_types": {
                        "title": "🏭 Warehouse Types",
                        "steps": [
                            "1️⃣ Inventory → Warehouse Types",
                            "2️⃣ Define types (Storage, Transit, Quarantine)",
                            "3️⃣ Set behavior rules per type",
                            "4️⃣ Configure stock availability rules",
                            "5️⃣ Link to transaction types",
                            "6️⃣ Apply to warehouses"
                        ],
                        "tips": [
                            "💡 Use quarantine for quality control",
                            "💡 Transit for in-transit stock",
                            "💡 Storage for regular inventory"
                        ]
                    },
                    "uom": {
                        "title": "⚖️ Units of Measure",
                        "steps": [
                            "1️⃣ Inventory → UoM",
                            "2️⃣ Add base UoM (Pieces, Kg, Liters)",
                            "3️⃣ Define UoM code and name",
                            "4️⃣ Set decimal places",
                            "5️⃣ Create multiple UoM per item",
                            "6️⃣ Link to UoM groups"
                        ],
                        "tips": [
                            "💡 Use consistent UoM across items",
                            "💡 Handle fractional quantities properly",
                            "💡 Convert between UoM accurately"
                        ]
                    },
                    "uom_groups": {
                        "title": "📊 UoM Groups",
                        "steps": [
                            "1️⃣ Inventory → UoM Groups",
                            "2️⃣ Create group (Weight, Volume, Count)",
                            "3️⃣ Add related UoMs",
                            "4️⃣ Set conversion factors",
                            "5️⃣ Define base UoM",
                            "6️⃣ Assign to items"
                        ],
                        "tips": [
                            "💡 Ensure conversion accuracy",
                            "💡 Test with sample items",
                            "💡 Document conversion rules"
                        ]
                    },
                    "shipping_types": {
                        "title": "🚚 Shipping Types",
                        "steps": [
                            "1️⃣ Inventory → Shipping Types",
                            "2️⃣ Define shipping methods (Standard, Express, Air)",
                            "3️⃣ Set delivery timeframes",
                            "4️⃣ Configure shipping costs",
                            "5️⃣ Link to carriers",
                            "6️⃣ Apply to deliveries"
                        ],
                        "tips": [
                            "💡 Offer customer choice",
                            "💡 Track carrier performance",
                            "💡 Optimize shipping costs"
                        ]
                    },
                    "item_defaults": {
                        "title": "⚙️ Item Defaults",
                        "steps": [
                            "1️⃣ Inventory → Item Defaults",
                            "2️⃣ Set default warehouse",
                            "3️⃣ Define default UoM",
                            "4️⃣ Configure default price list",
                            "5️⃣ Set default tax group",
                            "6️⃣ Apply to new items"
                        ],
                        "tips": [
                            "💡 Save time on item creation",
                            "💡 Ensure consistency",
                            "💡 Override when needed"
                        ]
                    },
                    "purchasing_inventory": {
                        "title": "📥 Purchasing Setup",
                        "sub_modules": {
                            "landed_costs_define": {
                                "title": "🚢 Landed Costs - Define",
                                "steps": [
                                    "1️⃣ Inventory → Purchasing → Landed Costs - Define",
                                    "2️⃣ Create cost types (Freight, Insurance, Customs)",
                                    "3️⃣ Set allocation method (Value, Weight, Volume)",
                                    "4️⃣ Define cost codes",
                                    "5️⃣ Link to purchase transactions",
                                    "6️⃣ Update item costs"
                                ],
                                "tips": [
                                    "💡 Include all import costs",
                                    "💡 Accurate allocation is critical",
                                    "💡 Review landed cost calculations"
                                ]
                            }
                        }
                    },
                    "bin_locations": {
                        "title": "📍 Bin Locations",
                        "steps": [
                            "1️⃣ Inventory → Bin Locations",
                            "2️⃣ Define bin structure (Aisle-Rack-Shelf-Bin)",
                            "3️⃣ Create bin codes",
                            "4️⃣ Assign to warehouses",
                            "5️⃣ Link items to bins",
                            "6️⃣ Track inventory by bin"
                        ],
                        "tips": [
                            "💡 Optimize warehouse layout",
                            "💡 Use for pick path optimization",
                            "💡 Enable cycle counting by bin"
                        ]
                    },
                    "field_activation": {
                        "title": "🔌 Field Activation",
                        "steps": [
                            "1️⃣ Inventory → Field Activation",
                            "2️⃣ Enable/disable item fields",
                            "3️⃣ Configure field visibility",
                            "4️⃣ Set mandatory fields",
                            "5️⃣ Customize for item types",
                            "6️⃣ Test with forms"
                        ],
                        "tips": [
                            "💡 Show only relevant fields",
                            "💡 Reduce clutter",
                            "💡 Ensure data completeness"
                        ]
                    },
                    "attributes_codes": {
                        "title": "🔖 Attributes Codes",
                        "steps": [
                            "1️⃣ Inventory → Attributes Codes",
                            "2️⃣ Define attribute categories",
                            "3️⃣ Create attribute values",
                            "4️⃣ Assign to items",
                            "5️⃣ Use in reporting",
                            "6️⃣ Enable attribute-based search"
                        ],
                        "tips": [
                            "💡 Use for product variants",
                            "💡 Enable better categorization",
                            "💡 Improve search results"
                        ]
                    },
                    "warehouse_sublevel_codes": {
                        "title": "📊 Warehouse Sublevel Codes",
                        "steps": [
                            "1️⃣ Inventory → Warehouse Sublevel Codes",
                            "2️⃣ Define sublevel hierarchy",
                            "3️⃣ Create sublevel codes",
                            "4️⃣ Assign to bin locations",
                            "5️⃣ Enable detailed tracking",
                            "6️⃣ Generate sublevel reports"
                        ],
                        "tips": [
                            "💡 Use for very large warehouses",
                            "💡 Improve picking accuracy",
                            "💡 Enable granular inventory tracking"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/inventory-master",
                "doc_url": "https://docs.leysco.com/inventory-master-guide",
                "estimated_time": "40 minutes",
                "prerequisites": ["Inventory access rights"],
                "keywords": ["inventory", "items", "warehouse", "uom", "bin", "groups"]
            },

            # =========================================================
            # 5. PRODUCTION MASTER DATA
            # =========================================================
            "production_master": {
                "id": "production_master",
                "title": "🏭 Production Master Data",
                "description": "Configure production and resource master data",
                "sub_modules": {
                    "resource_groups_prod": {
                        "title": "📋 Resource Groups",
                        "steps": [
                            "1️⃣ Production → Resource Groups",
                            "2️⃣ Create groups (Machines, Labor, Work Centers)",
                            "3️⃣ Set group capacity",
                            "4️⃣ Define operating hours",
                            "5️⃣ Assign resources",
                            "6️⃣ Track group utilization"
                        ],
                        "tips": [
                            "💡 Organize resources logically",
                            "💡 Balance workload across groups",
                            "💡 Monitor group efficiency"
                        ]
                    },
                    "resource_properties_prod": {
                        "title": "🏷️ Resource Properties",
                        "steps": [
                            "1️⃣ Production → Resource Properties",
                            "2️⃣ Define custom resource attributes",
                            "3️⃣ Set skill levels",
                            "4️⃣ Track certifications",
                            "5️⃣ Link to maintenance schedules",
                            "6️⃣ Enable resource matching"
                        ],
                        "tips": [
                            "💡 Capture all relevant resource info",
                            "💡 Track training requirements",
                            "💡 Schedule maintenance properly"
                        ]
                    },
                    "route_stages": {
                        "title": "🔄 Route Stages",
                        "steps": [
                            "1️⃣ Production → Route Stages",
                            "2️⃣ Define production stages",
                            "3️⃣ Set stage sequence",
                            "4️⃣ Assign resources to stages",
                            "5️⃣ Define stage durations",
                            "6️⃣ Link to BOMs"
                        ],
                        "tips": [
                            "💡 Map actual production flow",
                            "💡 Identify bottlenecks",
                            "💡 Optimize stage sequence"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/production-master",
                "doc_url": "https://docs.leysco.com/production-master-guide",
                "estimated_time": "20 minutes",
                "prerequisites": ["Production access rights"],
                "keywords": ["production", "resource", "route", "stage", "capacity"]
            },

            # =========================================================
            # 6. RESOURCES MASTER DATA
            # =========================================================
            "resources_master": {
                "id": "resources_master",
                "title": "🛠️ Resources Master Data",
                "description": "Configure all company resources",
                "sub_modules": {
                    "resource_groups_res": {
                        "title": "📋 Resource Groups",
                        "steps": [
                            "1️⃣ Resources → Resource Groups",
                            "2️⃣ Create resource categories",
                            "3️⃣ Set grouping criteria",
                            "4️⃣ Assign resources",
                            "5️⃣ Configure group reporting",
                            "6️⃣ Track group metrics"
                        ],
                        "tips": [
                            "💡 Align with organizational structure",
                            "💡 Simplify resource management",
                            "💡 Enable group-based reporting"
                        ]
                    },
                    "resource_properties_res": {
                        "title": "🏷️ Resource Properties",
                        "steps": [
                            "1️⃣ Resources → Resource Properties",
                            "2️⃣ Define custom resource fields",
                            "3️⃣ Set property values",
                            "4️⃣ Link to resources",
                            "5️⃣ Use in resource matching",
                            "6️⃣ Generate property reports"
                        ],
                        "tips": [
                            "💡 Capture all relevant attributes",
                            "💡 Enable better resource allocation",
                            "💡 Track specialized capabilities"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/resources-master",
                "doc_url": "https://docs.leysco.com/resources-master-guide",
                "estimated_time": "15 minutes",
                "prerequisites": ["Resource access rights"],
                "keywords": ["resource", "group", "property", "capacity"]
            },

            # =========================================================
            # 7. SERVICE MODULE
            # =========================================================
            "service": {
                "id": "service",
                "title": "🔧 Service Management",
                "description": "Configure customer service and contract templates",
                "sub_modules": {
                    "contract_template": {
                        "title": "📄 Contract Template",
                        "steps": [
                            "1️⃣ Service → Contract Template",
                            "2️⃣ Create service contract types",
                            "3️⃣ Define coverage terms",
                            "4️⃣ Set pricing structure",
                            "5️⃣ Configure renewal terms",
                            "6️⃣ Link to customers"
                        ],
                        "tips": [
                            "💡 Standardize contract offerings",
                            "💡 Track contract profitability",
                            "💡 Automate renewals"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/service",
                "doc_url": "https://docs.leysco.com/service-guide",
                "estimated_time": "10 minutes",
                "prerequisites": ["Service access rights"],
                "keywords": ["service", "contract", "warranty", "support"]
            },

            # =========================================================
            # 8. DATA IMPORTS / EXPORTS
            # =========================================================
            "data_imports_exports": {
                "id": "data_imports_exports",
                "title": "📤 Data Imports/Exports",
                "description": "Import and export data from various sources",
                "sub_modules": {
                    "import_from_excel": {
                        "title": "📊 Import from Excel",
                        "steps": [
                            "1️⃣ Data Imports/Exports → Import from Excel",
                            "2️⃣ Download template for data type",
                            "3️⃣ Prepare data in Excel",
                            "4️⃣ Map Excel columns to system fields",
                            "5️⃣ Validate data before import",
                            "6️⃣ Run import and review results"
                        ],
                        "tips": [
                            "💡 Always backup before import",
                            "💡 Validate data format",
                            "💡 Import in small batches"
                        ]
                    },
                    "import_from_sales_force": {
                        "title": "☁️ Import from Sales Force",
                        "steps": [
                            "1️⃣ Data Imports/Exports → Import from Sales Force",
                            "2️⃣ Connect to Sales Force account",
                            "3️⃣ Select data to import",
                            "4️⃣ Map fields",
                            "5️⃣ Run synchronization",
                            "6️⃣ Review imported data"
                        ],
                        "tips": [
                            "💡 Test with sample data first",
                            "💡 Schedule regular syncs",
                            "💡 Handle duplicate records"
                        ]
                    },
                    "data_export": {
                        "title": "📤 Data Export",
                        "steps": [
                            "1️⃣ Data Imports/Exports → Data Export",
                            "2️⃣ Select data to export",
                            "3️⃣ Choose export format (Excel, CSV, PDF)",
                            "4️⃣ Set filters and date ranges",
                            "5️⃣ Run export",
                            "6️⃣ Save or distribute file"
                        ],
                        "tips": [
                            "💡 Use for reporting and analysis",
                            "💡 Schedule regular exports",
                            "💡 Secure sensitive data"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/data-imports",
                "doc_url": "https://docs.leysco.com/data-guide",
                "estimated_time": "20 minutes",
                "prerequisites": ["System access"],
                "keywords": ["import", "export", "excel", "data", "migration"]
            },

            # =========================================================
            # 9. UTILITIES
            # =========================================================
            "utilities": {
                "id": "utilities",
                "title": "🔧 Utilities",
                "description": "System utilities, monitoring, and approval processes",
                "sub_modules": {
                    "connected_clients": {
                        "title": "💻 Connected Clients",
                        "steps": [
                            "1️⃣ Utilities → Connected Clients",
                            "2️⃣ View active user sessions",
                            "3️⃣ Monitor system usage",
                            "4️⃣ Disconnect idle sessions",
                            "5️⃣ Track login history",
                            "6️⃣ Investigate suspicious activity"
                        ],
                        "tips": [
                            "💡 Monitor concurrent usage",
                            "💡 Enforce session limits",
                            "💡 Log off inactive users"
                        ]
                    },
                    "approval_process": {
                        "title": "✓ Approval Process",
                        "sub_modules": {
                            "approval_stages": {
                                "title": "📊 Approval Stages",
                                "steps": [
                                    "1️⃣ Utilities → Approval Process → Approval Stages",
                                    "2️⃣ Define stage sequence",
                                    "3️⃣ Set stage conditions",
                                    "4️⃣ Assign approvers",
                                    "5️⃣ Configure escalation rules",
                                    "6️⃣ Test workflow"
                                ],
                                "tips": [
                                    "💡 Keep stages simple",
                                    "💡 Set realistic approval limits",
                                    "💡 Enable delegation"
                                ]
                            },
                            "approval_templates": {
                                "title": "📝 Approval Templates",
                                "steps": [
                                    "1️⃣ Utilities → Approval Process → Approval Templates",
                                    "2️⃣ Create template for document types",
                                    "3️⃣ Link to approval stages",
                                    "4️⃣ Set conditions (amount thresholds)",
                                    "5️⃣ Assign to documents",
                                    "6️⃣ Monitor effectiveness"
                                ],
                                "tips": [
                                    "💡 Create templates by document type",
                                    "💡 Differentiate by department",
                                    "💡 Review templates periodically"
                                ]
                            },
                            "approval_status_report": {
                                "title": "📋 Approval Status Report",
                                "steps": [
                                    "1️⃣ Utilities → Approval Process → Approval Status Report",
                                    "2️⃣ View pending approvals",
                                    "3️⃣ Track approval history",
                                    "4️⃣ Identify bottlenecks",
                                    "5️⃣ Monitor approval times",
                                    "6️⃣ Export for management"
                                ],
                                "tips": [
                                    "💡 Review daily",
                                    "💡 Follow up on pending items",
                                    "💡 Analyze approval patterns"
                                ]
                            },
                            "approval_decision_report": {
                                "title": "✓ Approval Decision Report",
                                "steps": [
                                    "1️⃣ Utilities → Approval Process → Approval Decision Report",
                                    "2️⃣ View decisions by approver",
                                    "3️⃣ Track approval rates",
                                    "4️⃣ Analyze rejection reasons",
                                    "5️⃣ Generate decision summaries",
                                    "6️⃣ Improve processes"
                                ],
                                "tips": [
                                    "💡 Monitor approver performance",
                                    "💡 Identify training needs",
                                    "💡 Adjust approval criteria"
                                ]
                            }
                        }
                    }
                },
                "video_url": "https://training.leysco.com/videos/utilities",
                "doc_url": "https://docs.leysco.com/utilities-guide",
                "estimated_time": "25 minutes",
                "prerequisites": ["System administrator access"],
                "keywords": ["utilities", "approval", "workflow", "monitoring"]
            },

            # =========================================================
            # 10. SALES TRANSACTIONS
            # =========================================================
            "sales_transactions": {
                "id": "sales_transactions",
                "title": "💼 Sales Transactions",
                "description": "Process all sales-related documents",
                "sub_modules": {
                    "quotations": {
                        "title": "📄 Quotations",
                        "steps": [
                            "1️⃣ Sales → Quotations → New",
                            "2️⃣ Select customer from Business Partners",
                            "3️⃣ Add items with quantities",
                            "4️⃣ Apply discounts if applicable",
                            "5️⃣ Set validity date",
                            "6️⃣ Print/email to customer"
                        ],
                        "tips": [
                            "💡 Copy existing quotes for repeat customers",
                            "💡 Track quote acceptance rate",
                            "💡 Set follow-up reminders"
                        ]
                    },
                    "sales_order": {
                        "title": "📦 Sales Order",
                        "steps": [
                            "1️⃣ Sales → Sales Order → New (or Copy from Quote)",
                            "2️⃣ Verify customer details",
                            "3️⃣ Check item availability",
                            "4️⃣ Confirm pricing and discounts",
                            "5️⃣ Set delivery date",
                            "6️⃣ Save and print order confirmation"
                        ],
                        "tips": [
                            "💡 Check credit limit before order",
                            "💡 Use blanket orders for contracts",
                            "💡 Monitor order backlog"
                        ]
                    },
                    "delivery": {
                        "title": "🚚 Delivery",
                        "steps": [
                            "1️⃣ Sales → Delivery → Create from Sales Order",
                            "2️⃣ Verify items to ship",
                            "3️⃣ Enter actual shipped quantities",
                            "4️⃣ Add tracking number",
                            "5️⃣ Print delivery note",
                            "6️⃣ Confirm goods issue"
                        ],
                        "tips": [
                            "💡 Partial deliveries supported",
                            "💡 Use barcode scanning",
                            "💡 Track delivery performance"
                        ]
                    },
                    "return_request": {
                        "title": "↩️ Return Request",
                        "steps": [
                            "1️⃣ Sales → Return Request → New",
                            "2️⃣ Select customer and order",
                            "3️⃣ Enter items to return",
                            "4️⃣ Specify return reason",
                            "5️⃣ Submit for approval",
                            "6️⃣ Track request status"
                        ],
                        "tips": [
                            "💡 Require RMA numbers",
                            "💡 Inspect returns promptly",
                            "💡 Track return reasons"
                        ]
                    },
                    "return": {
                        "title": "↩️ Return",
                        "steps": [
                            "1️⃣ Sales → Return → Create from Return Request",
                            "2️⃣ Verify returned items",
                            "3️⃣ Inspect condition",
                            "4️⃣ Process refund/replacement",
                            "5️⃣ Update inventory",
                            "6️⃣ Generate credit memo"
                        ],
                        "tips": [
                            "💡 Inspect before processing",
                            "💡 Restock sellable items",
                            "💡 Dispose of damaged goods"
                        ]
                    },
                    "ar_invoice": {
                        "title": "🧾 A/R Invoice",
                        "steps": [
                            "1️⃣ Sales → A/R Invoice → Create from Delivery",
                            "2️⃣ Verify all items billed",
                            "3️⃣ Confirm taxes",
                            "4️⃣ Add invoice number",
                            "5️⃣ Print and email",
                            "6️⃣ Post to accounts"
                        ],
                        "tips": [
                            "💡 Include PO number on invoice",
                            "💡 Send immediately after delivery",
                            "💡 Track aging reports"
                        ]
                    },
                    "ar_credit_memo": {
                        "title": "↩️ A/R Credit Memo",
                        "steps": [
                            "1️⃣ Sales → A/R Credit Memo → New",
                            "2️⃣ Select reason",
                            "3️⃣ Link to original invoice",
                            "4️⃣ Enter credited items",
                            "5️⃣ Add notes",
                            "6️⃣ Post to customer account"
                        ],
                        "tips": [
                            "💡 Require approval",
                            "💡 Track return reasons",
                            "💡 Apply to open invoices"
                        ]
                    },
                    "ar_reserve_invoice": {
                        "title": "📋 A/R Reserve Invoice",
                        "steps": [
                            "1️⃣ Sales → A/R Reserve Invoice → New",
                            "2️⃣ Create for future billing",
                            "3️⃣ Set reservation details",
                            "4️⃣ Convert to invoice when ready",
                            "5️⃣ Track reserved amounts",
                            "6️⃣ Release when billed"
                        ],
                        "tips": [
                            "💡 Use for recurring billing",
                            "💡 Track commitments",
                            "💡 Convert at billing time"
                        ]
                    },
                    "ar_invoice_payment": {
                        "title": "💳 A/R Invoice + Payment",
                        "steps": [
                            "1️⃣ Sales → A/R Invoice + Payment → New",
                            "2️⃣ Create invoice and record payment",
                            "3️⃣ Select payment method",
                            "4️⃣ Enter payment amount",
                            "5️⃣ Apply to invoice",
                            "6️⃣ Post and close"
                        ],
                        "tips": [
                            "💡 Use for cash sales",
                            "💡 Record payment immediately",
                            "💡 Reduce receivables"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/sales",
                "doc_url": "https://docs.leysco.com/sales-guide",
                "estimated_time": "35 minutes",
                "prerequisites": ["Sales access rights"],
                "keywords": ["sales", "order", "invoice", "delivery", "return", "quote"]
            },

            # =========================================================
            # 11. PURCHASE - A/P TRANSACTIONS
            # =========================================================
            "purchase_transactions": {
                "id": "purchase_transactions",
                "title": "📥 Purchase Transactions",
                "description": "Process all purchasing and vendor documents",
                "sub_modules": {
                    "purchase_request": {
                        "title": "📋 Purchase Request",
                        "steps": [
                            "1️⃣ Purchase -A/P → Purchase Request → New",
                            "2️⃣ Enter requested items",
                            "3️⃣ Specify required date",
                            "4️⃣ Add justification",
                            "5️⃣ Submit for approval",
                            "6️⃣ Track status"
                        ],
                        "tips": [
                            "💡 Set approval workflow",
                            "💡 Link to projects",
                            "💡 Consolidate requests"
                        ]
                    },
                    "purchase_quotation": {
                        "title": "📄 Purchase Quotation",
                        "steps": [
                            "1️⃣ Purchase -A/P → Purchase Quotation → New",
                            "2️⃣ Select vendors",
                            "3️⃣ Request quotes",
                            "4️⃣ Enter received quotes",
                            "5️⃣ Compare pricing",
                            "6️⃣ Select best offer"
                        ],
                        "tips": [
                            "💡 Get multiple quotes",
                            "💡 Track vendor pricing",
                            "💡 Negotiate better rates"
                        ]
                    },
                    "purchase_order": {
                        "title": "📑 Purchase Order",
                        "steps": [
                            "1️⃣ Purchase -A/P → Purchase Order → New",
                            "2️⃣ Select vendor",
                            "3️⃣ Add items and quantities",
                            "4️⃣ Confirm prices",
                            "5️⃣ Set delivery date",
                            "6️⃣ Send to vendor"
                        ],
                        "tips": [
                            "💡 Use blanket POs for long-term",
                            "💡 Track PO status",
                            "💡 Set up automatic generation"
                        ]
                    },
                    "goods_receipt_po": {
                        "title": "📦 Goods Receipt PO",
                        "steps": [
                            "1️⃣ Purchase -A/P → Good Receipt PO → New",
                            "2️⃣ Select purchase order",
                            "3️⃣ Verify received items",
                            "4️⃣ Enter received quantities",
                            "5️⃣ Note discrepancies",
                            "6️⃣ Post to inventory"
                        ],
                        "tips": [
                            "💡 Inspect goods before accepting",
                            "💡 Record partial receipts",
                            "💡 Update quality results"
                        ]
                    },
                    "goods_return_request": {
                        "title": "↩️ Goods Return Request",
                        "steps": [
                            "1️⃣ Purchase -A/P → Goods Return Request → New",
                            "2️⃣ Link to goods receipt",
                            "3️⃣ Select items to return",
                            "4️⃣ Specify return reason",
                            "5️⃣ Submit request",
                            "6️⃣ Track status"
                        ],
                        "tips": [
                            "💡 Get RMA from vendor",
                            "💡 Inspect before return",
                            "💡 Document reasons"
                        ]
                    },
                    "goods_return": {
                        "title": "↩️ Goods Return",
                        "steps": [
                            "1️⃣ Purchase -A/P → Goods Return → New",
                            "2️⃣ Create from return request",
                            "3️⃣ Verify return items",
                            "4️⃣ Generate return delivery",
                            "5️⃣ Process credit memo",
                            "6️⃣ Update inventory"
                        ],
                        "tips": [
                            "💡 Get return authorization",
                            "💡 Track return status",
                            "💡 Follow up on credits"
                        ]
                    },
                    "ap_invoice": {
                        "title": "🧾 A/P Invoice",
                        "steps": [
                            "1️⃣ Purchase -A/P → A/P Invoice → New",
                            "2️⃣ Link to goods receipt",
                            "3️⃣ Verify invoice details",
                            "4️⃣ Enter invoice number",
                            "5️⃣ Confirm amounts",
                            "6️⃣ Post for payment"
                        ],
                        "tips": [
                            "💡 Use 3-way matching",
                            "💡 Flag discrepancies",
                            "💡 Take early payment discounts"
                        ]
                    },
                    "ap_credit_memo": {
                        "title": "↩️ A/P Credit Memo",
                        "steps": [
                            "1️⃣ Purchase -A/P → A/P Credit Memo → New",
                            "2️⃣ Link to goods return",
                            "3️⃣ Enter credit amount",
                            "4️⃣ Add reference",
                            "5️⃣ Post to vendor account",
                            "6️⃣ Apply to future invoices"
                        ],
                        "tips": [
                            "💡 Track vendor credits",
                            "💡 Apply promptly",
                            "💡 Follow up on discrepancies"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/purchase",
                "doc_url": "https://docs.leysco.com/purchase-guide",
                "estimated_time": "35 minutes",
                "prerequisites": ["Purchasing access rights"],
                "keywords": ["purchase", "po", "vendor", "goods receipt", "invoice"]
            },

            # =========================================================
            # 12. BUSINESS PARTNERS TRANSACTIONS
            # =========================================================
            "business_partners_trans": {
                "id": "business_partners_trans",
                "title": "👥 Business Partners",
                "description": "Manage customer and vendor master data",
                "sub_modules": {
                    "bp_master_data": {
                        "title": "📋 BP Master Data",
                        "steps": [
                            "1️⃣ Business Partners → BP Master Data",
                            "2️⃣ Search for existing partner",
                            "3️⃣ Create new customer/vendor",
                            "4️⃣ Enter all contact details",
                            "5️⃣ Set payment terms and price lists",
                            "6️⃣ Save and verify"
                        ],
                        "tips": [
                            "💡 Verify all details for accuracy",
                            "💡 Set up credit limits",
                            "💡 Link contacts properly"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/bp",
                "doc_url": "https://docs.leysco.com/bp-guide",
                "estimated_time": "15 minutes",
                "prerequisites": ["BP access rights"],
                "keywords": ["customer", "vendor", "partner", "master data"]
            },

            # =========================================================
            # 13. BANKING TRANSACTIONS
            # =========================================================
            "banking_transactions": {
                "id": "banking_transactions",
                "title": "💳 Banking Transactions",
                "description": "Process all banking and payment transactions",
                "sub_modules": {
                    "incoming_payments": {
                        "title": "💰 Incoming Payments",
                        "sub_modules": {
                            "third_party_payments": {
                                "title": "🤝 Third Party Payments",
                                "steps": [
                                    "1️⃣ Banking → Incoming Payments → Third Party Payments",
                                    "2️⃣ Select customer",
                                    "3️⃣ Enter payment amount",
                                    "4️⃣ Choose payment method",
                                    "5️⃣ Apply to invoices",
                                    "6️⃣ Post payment"
                                ],
                                "tips": [
                                    "💡 Verify payer identity",
                                    "💡 Record references",
                                    "💡 Apply to correct invoices"
                                ]
                            },
                            "incoming_payments_main": {
                                "title": "💵 Incoming Payments",
                                "steps": [
                                    "1️⃣ Banking → Incoming Payments → Incoming Payments",
                                    "2️⃣ Select customer",
                                    "3️⃣ View open invoices",
                                    "4️⃣ Apply payment to invoices",
                                    "5️⃣ Enter reference number",
                                    "6️⃣ Post and generate receipt"
                                ],
                                "tips": [
                                    "💡 Match payments accurately",
                                    "💡 Handle partial payments",
                                    "💡 Record payment method"
                                ]
                            }
                        }
                    },
                    "deposits": {
                        "title": "🏦 Deposits",
                        "sub_modules": {
                            "deposits_main": {
                                "title": "📥 Deposits",
                                "steps": [
                                    "1️⃣ Banking → Deposits → Deposits",
                                    "2️⃣ Select received payments",
                                    "3️⃣ Enter deposit date",
                                    "4️⃣ Add deposit slip number",
                                    "5️⃣ Confirm total",
                                    "6️⃣ Post to bank"
                                ],
                                "tips": [
                                    "💡 Deposit daily",
                                    "💡 Keep deposit slips",
                                    "💡 Reconcile with bank"
                                ]
                            },
                            "postdated_check_deposit": {
                                "title": "📅 Postdated Check Deposit",
                                "steps": [
                                    "1️⃣ Banking → Deposits → Postdated Check Deposit",
                                    "2️⃣ Enter check details",
                                    "3️⃣ Set future date",
                                    "4️⃣ Hold until date",
                                    "5️⃣ Deposit on due date",
                                    "6️⃣ Track check status"
                                ],
                                "tips": [
                                    "💡 Verify check validity",
                                    "💡 Track postdated items",
                                    "💡 Deposit on due date"
                                ]
                            },
                            "postdated_credit_voucher": {
                                "title": "📝 Postdated Credit Voucher",
                                "steps": [
                                    "1️⃣ Banking → Deposits → Postdated Credit Voucher",
                                    "2️⃣ Create credit voucher",
                                    "3️⃣ Set future date",
                                    "4️⃣ Hold until maturity",
                                    "5️⃣ Apply on due date",
                                    "6️⃣ Track voucher status"
                                ],
                                "tips": [
                                    "💡 Use for future commitments",
                                    "💡 Track maturity dates",
                                    "💡 Apply promptly"
                                ]
                            }
                        }
                    },
                    "outgoing_payments": {
                        "title": "💸 Outgoing Payments",
                        "sub_modules": {
                            "on_vendor_customers": {
                                "title": "🤝 On Vendor|Customers",
                                "steps": [
                                    "1️⃣ Banking → Outgoing Payments → On Vendor|Customers",
                                    "2️⃣ Select vendor",
                                    "3️⃣ View open payables",
                                    "4️⃣ Enter payment amount",
                                    "5️⃣ Choose payment method",
                                    "6️⃣ Post payment"
                                ],
                                "tips": [
                                    "💡 Schedule payments",
                                    "💡 Take discounts",
                                    "💡 Record accurately"
                                ]
                            },
                            "on_account": {
                                "title": "💳 On Account",
                                "steps": [
                                    "1️⃣ Banking → Outgoing Payments → On Account",
                                    "2️⃣ Select vendor",
                                    "3️⃣ Enter prepayment amount",
                                    "4️⃣ Record purpose",
                                    "5️⃣ Post to vendor account",
                                    "6️⃣ Apply to future invoices"
                                ],
                                "tips": [
                                    "💡 Use for deposits",
                                    "💡 Track prepayments",
                                    "💡 Apply when invoiced"
                                ]
                            },
                            "checks_for_payment": {
                                "title": "📝 Checks for Payment",
                                "steps": [
                                    "1️⃣ Banking → Outgoing Payments → Checks for Payment",
                                    "2️⃣ Select payments to make",
                                    "3️⃣ Generate checks",
                                    "4️⃣ Print checks",
                                    "5️⃣ Record check numbers",
                                    "6️⃣ Mail to vendors"
                                ],
                                "tips": [
                                    "💡 Secure check stock",
                                    "💡 Use check printing templates",
                                    "💡 Void spoiled checks"
                                ]
                            }
                        }
                    },
                    "bank_statements_reconciliation": {
                        "title": "📊 Bank Statements and Ext Reconciliation",
                        "sub_modules": {
                            "reconciliation": {
                                "title": "🔄 Reconciliation",
                                "steps": [
                                    "1️⃣ Banking → Bank Statements and Ext Reconciliation → Reconciliation",
                                    "2️⃣ Select bank account",
                                    "3️⃣ Enter ending balance",
                                    "4️⃣ Match transactions",
                                    "5️⃣ Investigate differences",
                                    "6️⃣ Complete reconciliation"
                                ],
                                "tips": [
                                    "💡 Reconcile monthly",
                                    "💡 Document differences",
                                    "💡 Clear old items"
                                ]
                            },
                            "manual_reconciliation": {
                                "title": "✍️ Manual Reconciliation",
                                "steps": [
                                    "1️⃣ Banking → Bank Statements and Ext Reconciliation → Manual Reconciliation",
                                    "2️⃣ Manually match transactions",
                                    "3️⃣ Create adjusting entries",
                                    "4️⃣ Document reasons",
                                    "5️⃣ Post adjustments",
                                    "6️⃣ Verify balances"
                                ],
                                "tips": [
                                    "💡 Use for complex items",
                                    "💡 Document thoroughly",
                                    "💡 Review after posting"
                                ]
                            },
                            "previous_ext_reconciliation": {
                                "title": "📋 Previous Ext Reconciliation",
                                "steps": [
                                    "1️⃣ Banking → Bank Statements and Ext Reconciliation → Previous Ext Reconciliation",
                                    "2️⃣ View reconciliation history",
                                    "3️⃣ Review past reconciliations",
                                    "4️⃣ Reprint reports",
                                    "5️⃣ Audit trail",
                                    "6️⃣ Export for records"
                                ],
                                "tips": [
                                    "💡 Keep reconciliation history",
                                    "💡 Use for audits",
                                    "💡 Review for accuracy"
                                ]
                            },
                            "check_restore_pre_ext_reconciliation": {
                                "title": "🔄 Check and Restore Pre Ext Reconciliation",
                                "steps": [
                                    "1️⃣ Banking → Bank Statements and Ext Reconciliation → Check and Restore Pre Ext Reconciliation",
                                    "2️⃣ Select reconciliation to restore",
                                    "3️⃣ Review items",
                                    "4️⃣ Confirm restoration",
                                    "5️⃣ Re-reconcile if needed",
                                    "6️⃣ Document changes"
                                ],
                                "tips": [
                                    "💡 Use only when necessary",
                                    "💡 Document reasons",
                                    "💡 Reconcile again after"
                                ]
                            }
                        }
                    }
                },
                "video_url": "https://training.leysco.com/videos/banking-transactions",
                "doc_url": "https://docs.leysco.com/banking-transactions-guide",
                "estimated_time": "45 minutes",
                "prerequisites": ["Finance access rights"],
                "keywords": ["payment", "deposit", "reconciliation", "check", "bank"]
            },

            # =========================================================
            # 14. INVENTORY TRANSACTIONS
            # =========================================================
            "inventory_transactions": {
                "id": "inventory_transactions",
                "title": "📊 Inventory Transactions",
                "description": "Manage all inventory movements and reports",
                "sub_modules": {
                    "item_management": {
                        "title": "📦 Item Management",
                        "sub_modules": {
                            "item_master_data": {
                                "title": "📋 Item Master Data",
                                "steps": [
                                    "1️⃣ Inventory → Item Management → Item Master data",
                                    "2️⃣ Search for existing items",
                                    "3️⃣ Create new item",
                                    "4️⃣ Enter all item details",
                                    "5️⃣ Set prices and UoM",
                                    "6️⃣ Save and verify"
                                ],
                                "tips": [
                                    "💡 Use consistent naming",
                                    "💡 Include images",
                                    "💡 Set up all properties"
                                ]
                            }
                        }
                    },
                    "inventory_transactions_main": {
                        "title": "🔄 Inventory Transactions",
                        "sub_modules": {
                            "goods_receipt": {
                                "title": "📥 Goods Receipt",
                                "steps": [
                                    "1️⃣ Inventory → Inventory Transactions → Goods Receipt",
                                    "2️⃣ Select receipt type",
                                    "3️⃣ Enter items received",
                                    "4️⃣ Choose warehouse",
                                    "5️⃣ Add reference",
                                    "6️⃣ Post to inventory"
                                ],
                                "tips": [
                                    "💡 Verify quantities",
                                    "💡 Inspect quality",
                                    "💡 Update immediately"
                                ]
                            },
                            "inventory_stock_report": {
                                "title": "📊 Inventory Stock Report",
                                "steps": [
                                    "1️⃣ Inventory → Inventory Transactions → Inventory Stock Report",
                                    "2️⃣ Set report parameters",
                                    "3️⃣ Select warehouses",
                                    "4️⃣ Run report",
                                    "5️⃣ Review stock levels",
                                    "6️⃣ Export if needed"
                                ],
                                "tips": [
                                    "💡 Review daily",
                                    "💡 Investigate discrepancies",
                                    "💡 Use for planning"
                                ]
                            },
                            "inventory_counting": {
                                "title": "🔢 Inventory Counting",
                                "steps": [
                                    "1️⃣ Inventory → Inventory Transactions → Inventory Counting",
                                    "2️⃣ Create counting session",
                                    "3️⃣ Print count sheets",
                                    "4️⃣ Enter counted quantities",
                                    "5️⃣ Investigate variances",
                                    "6️⃣ Post adjustments"
                                ],
                                "tips": [
                                    "💡 Count regularly",
                                    "💡 Cycle count high-value items",
                                    "💡 Document reasons"
                                ]
                            },
                            "goods_issue": {
                                "title": "📤 Goods Issue",
                                "steps": [
                                    "1️⃣ Inventory → Inventory Transactions → Goods Issue",
                                    "2️⃣ Select issue type",
                                    "3️⃣ Enter items issued",
                                    "4️⃣ Choose warehouse",
                                    "5️⃣ Add reason/reference",
                                    "6️⃣ Post reduction"
                                ],
                                "tips": [
                                    "💡 Use for non-sales issues",
                                    "💡 Document purpose",
                                    "💡 Track samples/damages"
                                ]
                            },
                            "inventory_transfer_request": {
                                "title": "📝 Inventory Transfer Request",
                                "steps": [
                                    "1️⃣ Inventory → Inventory Transactions → Inventory Transfer Request",
                                    "2️⃣ Create transfer request",
                                    "3️⃣ Select from/to warehouses",
                                    "4️⃣ Add items and quantities",
                                    "5️⃣ Submit for approval",
                                    "6️⃣ Track status"
                                ],
                                "tips": [
                                    "💡 Require approval",
                                    "💡 Track in-transit",
                                    "💡 Complete promptly"
                                ]
                            },
                            "inventory_transfer": {
                                "title": "🔄 Inventory Transfer",
                                "steps": [
                                    "1️⃣ Inventory → Inventory Transactions → Inventory Transfer",
                                    "2️⃣ Create from transfer request",
                                    "3️⃣ Confirm quantities",
                                    "4️⃣ Execute transfer",
                                    "5️⃣ Update both warehouses",
                                    "6️⃣ Verify completion"
                                ],
                                "tips": [
                                    "💡 Verify receipt",
                                    "💡 Track transfer time",
                                    "💡 Investigate discrepancies"
                                ]
                            }
                        }
                    },
                    "price_list": {
                        "title": "💰 Price List",
                        "sub_modules": {
                            "price_list_main": {
                                "title": "📋 Price List",
                                "steps": [
                                    "1️⃣ Inventory → Price List → Price List",
                                    "2️⃣ Create new price list",
                                    "3️⃣ Add items with prices",
                                    "4️⃣ Set effective dates",
                                    "5️⃣ Assign to customers",
                                    "6️⃣ Update as needed"
                                ],
                                "tips": [
                                    "💡 Maintain multiple lists",
                                    "💡 Review regularly",
                                    "💡 Adjust for market"
                                ]
                            },
                            "period_and_volume_discounts": {
                                "title": "📅 Period and Volume Discounts",
                                "steps": [
                                    "1️⃣ Inventory → Price List → Period and Volume Discounts",
                                    "2️⃣ Create discount rules",
                                    "3️⃣ Set discount percentages",
                                    "4️⃣ Define qualifying quantities",
                                    "5️⃣ Set date ranges",
                                    "6️⃣ Apply to items"
                                ],
                                "tips": [
                                    "💡 Use for promotions",
                                    "💡 Encourage volume",
                                    "💡 Monitor effectiveness"
                                ]
                            },
                            "discount_groups": {
                                "title": "🏷️ Discount Groups",
                                "steps": [
                                    "1️⃣ Inventory → Price List → Discount Groups",
                                    "2️⃣ Create discount groups",
                                    "3️⃣ Set group discounts",
                                    "4️⃣ Assign items to groups",
                                    "5️⃣ Link to customer groups",
                                    "6️⃣ Apply automatically"
                                ],
                                "tips": [
                                    "💡 Simplify discount management",
                                    "💡 Apply consistently",
                                    "💡 Review group structure"
                                ]
                            },
                            "promotion_items": {
                                "title": "🎉 Promotion Items",
                                "steps": [
                                    "1️⃣ Inventory → Price List → Promotion Items",
                                    "2️⃣ Select items for promotion",
                                    "3️⃣ Set promotional price",
                                    "4️⃣ Define promotion dates",
                                    "5️⃣ Add promotion code",
                                    "6️⃣ Track performance"
                                ],
                                "tips": [
                                    "💡 Plan promotions strategically",
                                    "💡 Monitor uplift",
                                    "💡 End on schedule"
                                ]
                            }
                        }
                    },
                    "reports_inventory": {
                        "title": "📊 Reports",
                        "sub_modules": {
                            "stock_balances_report": {
                                "title": "⚖️ Stock Balances Report",
                                "steps": [
                                    "1️⃣ Inventory → Reports → Stock Balances Report",
                                    "2️⃣ Select date range",
                                    "3️⃣ Choose warehouses",
                                    "4️⃣ Run report",
                                    "5️⃣ Review balances",
                                    "6️⃣ Export for analysis"
                                ],
                                "tips": [
                                    "💡 Review regularly",
                                    "💡 Investigate anomalies",
                                    "💡 Use for planning"
                                ]
                            },
                            "stock_movement": {
                                "title": "🔄 Stock Movement",
                                "steps": [
                                    "1️⃣ Inventory → Reports → Stock Movement",
                                    "2️⃣ Select date range",
                                    "3️⃣ Choose items",
                                    "4️⃣ Run report",
                                    "5️⃣ Analyze movement patterns",
                                    "6️⃣ Identify trends"
                                ],
                                "tips": [
                                    "💡 Monitor fast/slow movers",
                                    "💡 Adjust reorder points",
                                    "💡 Plan promotions"
                                ]
                            },
                            "opening_balance": {
                                "title": "📅 Opening Balance",
                                "steps": [
                                    "1️⃣ Inventory → Reports → Opening Balance",
                                    "2️⃣ Select period",
                                    "3️⃣ View opening balances",
                                    "4️⃣ Verify accuracy",
                                    "5️⃣ Compare to closing",
                                    "6️⃣ Adjust if needed"
                                ],
                                "tips": [
                                    "💡 Verify at period start",
                                    "💡 Use for audits",
                                    "💡 Document adjustments"
                                ]
                            },
                            "stock_cumulative_balances": {
                                "title": "📊 Stock Cumulative Balances",
                                "steps": [
                                    "1️⃣ Inventory → Reports → Stock Cumulative Balances",
                                    "2️⃣ Set date range",
                                    "3️⃣ Run cumulative report",
                                    "4️⃣ Review trends",
                                    "5️⃣ Export for analysis",
                                    "6️⃣ Plan inventory"
                                ],
                                "tips": [
                                    "💡 Track long-term trends",
                                    "💡 Forecast demand",
                                    "💡 Plan purchases"
                                ]
                            },
                            "stock_top_moving_items": {
                                "title": "📈 Stock Top Moving Items",
                                "steps": [
                                    "1️⃣ Inventory → Reports → Stock Top Moving Items",
                                    "2️⃣ Select period",
                                    "3️⃣ Run report",
                                    "4️⃣ Identify top movers",
                                    "5️⃣ Ensure stock levels",
                                    "6️⃣ Plan promotions"
                                ],
                                "tips": [
                                    "💡 Keep top movers in stock",
                                    "💡 Negotiate better prices",
                                    "💡 Feature in promotions"
                                ]
                            },
                            "stock_balance": {
                                "title": "⚖️ Stock Balance",
                                "steps": [
                                    "1️⃣ Inventory → Reports → Stock Balance",
                                    "2️⃣ Select items",
                                    "3️⃣ View current balances",
                                    "4️⃣ Check availability",
                                    "5️⃣ Identify shortages",
                                    "6️⃣ Reorder as needed"
                                ],
                                "tips": [
                                    "💡 Check before promising",
                                    "💡 Monitor daily",
                                    "💡 Set up alerts"
                                ]
                            },
                            "serials_report": {
                                "title": "🔖 Serials Report",
                                "steps": [
                                    "1️⃣ Inventory → Reports → Serials Report",
                                    "2️⃣ Select serial numbers",
                                    "3️⃣ View serial details",
                                    "4️⃣ Track serial status",
                                    "5️⃣ Trace history",
                                    "6️⃣ Export for warranty"
                                ],
                                "tips": [
                                    "💡 Use for warranty tracking",
                                    "💡 Trace issues",
                                    "💡 Maintain records"
                                ]
                            },
                            "bin_locations_reports": {
                                "title": "📍 Bin Locations Reports",
                                "sub_modules": {
                                    "bin_locations": {
                                        "title": "🗺️ Bin Locations",
                                        "steps": [
                                            "1️⃣ Inventory → Reports → Bin Locations Reports → Bin Locations",
                                            "2️⃣ Select warehouse",
                                            "3️⃣ View bin contents",
                                            "4️⃣ Check bin utilization",
                                            "5️⃣ Optimize placement",
                                            "6️⃣ Cycle count by bin"
                                        ],
                                        "tips": [
                                            "💡 Organize efficiently",
                                            "💡 Use for picking",
                                            "💡 Maintain accuracy"
                                        ]
                                    }
                                }
                            }
                        }
                    }
                },
                "video_url": "https://training.leysco.com/videos/inventory-transactions",
                "doc_url": "https://docs.leysco.com/inventory-transactions-guide",
                "estimated_time": "50 minutes",
                "prerequisites": ["Inventory access rights"],
                "keywords": ["inventory", "stock", "transfer", "count", "report", "price"]
            },

            # =========================================================
            # 15. RESOURCES MANAGEMENT
            # =========================================================
            "resources_management": {
                "id": "resources_management",
                "title": "🛠️ Resources Management",
                "description": "Manage all company resources, capacity, and availability",
                "sub_modules": {
                    "resource_master_data": {
                        "title": "📋 Resource Master Data",
                        "steps": [
                            "1️⃣ Resources → Resource Master Data",
                            "2️⃣ Create new resource",
                            "3️⃣ Enter resource details",
                            "4️⃣ Assign to group",
                            "5️⃣ Set capacity",
                            "6️⃣ Save and verify"
                        ],
                        "tips": [
                            "💡 Track all resources",
                            "💡 Maintain accurate data",
                            "💡 Update as needed"
                        ]
                    },
                    "resource_groups_res_mgmt": {
                        "title": "👥 Resource Groups",
                        "steps": [
                            "1️⃣ Resources → Resource Groups",
                            "2️⃣ Create resource groups",
                            "3️⃣ Assign resources",
                            "4️⃣ Set group capacity",
                            "5️⃣ Monitor utilization",
                            "6️⃣ Adjust as needed"
                        ],
                        "tips": [
                            "💡 Group similar resources",
                            "💡 Balance workload",
                            "💡 Track group performance"
                        ]
                    },
                    "warehouse_assignments": {
                        "title": "🏭 Warehouse Assignments",
                        "steps": [
                            "1️⃣ Resources → Warehouse Assignments",
                            "2️⃣ Assign resources to warehouses",
                            "3️⃣ Set availability by location",
                            "4️⃣ Track resource location",
                            "5️⃣ Optimize assignments",
                            "6️⃣ Update as needed"
                        ],
                        "tips": [
                            "💡 Know resource locations",
                            "💡 Plan movements",
                            "💡 Track utilization by site"
                        ]
                    },
                    "resource_pricing": {
                        "title": "💰 Resource Pricing",
                        "steps": [
                            "1️⃣ Resources → Resource Pricing",
                            "2️⃣ Set hourly/daily rates",
                            "3️⃣ Define cost rates",
                            "4️⃣ Link to projects",
                            "5️⃣ Calculate resource costs",
                            "6️⃣ Review profitability"
                        ],
                        "tips": [
                            "💡 Track resource costs",
                            "💡 Price services appropriately",
                            "💡 Monitor profitability"
                        ]
                    },
                    "capacity_management": {
                        "title": "📊 Capacity Management",
                        "steps": [
                            "1️⃣ Resources → Capacity Management",
                            "2️⃣ View resource capacity",
                            "3️⃣ Check utilization",
                            "4️⃣ Identify bottlenecks",
                            "5️⃣ Plan capacity needs",
                            "6️⃣ Adjust schedules"
                        ],
                        "tips": [
                            "💡 Monitor regularly",
                            "💡 Plan for peak times",
                            "💡 Avoid overloading"
                        ]
                    },
                    "item_compatibility": {
                        "title": "🔗 Item Compatibility",
                        "steps": [
                            "1️⃣ Resources → Item Compatibility",
                            "2️⃣ Link resources to items",
                            "3️⃣ Define compatible resources",
                            "4️⃣ Set resource requirements",
                            "5️⃣ Check availability",
                            "6️⃣ Schedule accordingly"
                        ],
                        "tips": [
                            "💡 Know resource needs",
                            "💡 Plan production",
                            "💡 Avoid conflicts"
                        ]
                    },
                    "employee_qualifications": {
                        "title": "📜 Employee Qualifications",
                        "steps": [
                            "1️⃣ Resources → Employee Qualifications",
                            "2️⃣ Track employee skills",
                            "3️⃣ Record certifications",
                            "4️⃣ Set qualification levels",
                            "5️⃣ Match to requirements",
                            "6️⃣ Plan training"
                        ],
                        "tips": [
                            "💡 Maintain skills database",
                            "💡 Track certification expiry",
                            "💡 Plan development"
                        ]
                    },
                    "vendor_management": {
                        "title": "🤝 Vendor Management",
                        "steps": [
                            "1️⃣ Resources → Vendor Management",
                            "2️⃣ Manage vendor resources",
                            "3️⃣ Track vendor contracts",
                            "4️⃣ Monitor vendor performance",
                            "5️⃣ Rate vendors",
                            "6️⃣ Update vendor info"
                        ],
                        "tips": [
                            "💡 Track external resources",
                            "💡 Evaluate performance",
                            "💡 Maintain relationships"
                        ]
                    },
                    "resource_availability": {
                        "title": "✅ Resource Availability",
                        "steps": [
                            "1️⃣ Resources → Resource Availability",
                            "2️⃣ Check resource availability",
                            "3️⃣ View schedules",
                            "4️⃣ Identify free resources",
                            "5️⃣ Book resources",
                            "6️⃣ Track utilization"
                        ],
                        "tips": [
                            "💡 Check before scheduling",
                            "💡 Avoid double-booking",
                            "💡 Update availability"
                        ]
                    },
                    "resource_reports": {
                        "title": "📊 Resource Reports",
                        "steps": [
                            "1️⃣ Resources → Resource Reports",
                            "2️⃣ Run utilization reports",
                            "3️⃣ Analyze costs",
                            "4️⃣ View availability",
                            "5️⃣ Export for management",
                            "6️⃣ Plan improvements"
                        ],
                        "tips": [
                            "💡 Review regularly",
                            "💡 Identify trends",
                            "💡 Optimize resource use"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/resources",
                "doc_url": "https://docs.leysco.com/resources-guide",
                "estimated_time": "35 minutes",
                "prerequisites": ["Resource access rights"],
                "keywords": ["resource", "capacity", "availability", "pricing", "qualification"]
            },

            # =========================================================
            # 16. LOGISTICS HUB
            # =========================================================
            "logistics_hub": {
                "id": "logistics_hub",
                "title": "🚚 Logistics Hub",
                "description": "Complete logistics, route management, and dispatch",
                "sub_modules": {
                    "dashboard_logistics": {
                        "title": "📊 Dashboard",
                        "steps": [
                            "1️⃣ Logistics Hub → Dashboard",
                            "2️⃣ View logistics overview",
                            "3️⃣ Monitor active routes",
                            "4️⃣ Check pending deliveries",
                            "5️⃣ Review vehicle status",
                            "6️⃣ Track key metrics"
                        ],
                        "tips": [
                            "💡 Review daily",
                            "💡 Identify issues",
                            "💡 Monitor performance"
                        ]
                    },
                    "setup_logistics": {
                        "title": "⚙️ Setup",
                        "sub_modules": {
                            "sat_settings": {
                                "title": "🛰️ SAT Settings",
                                "steps": [
                                    "1️⃣ Logistics Hub → Setup → SAT Settings",
                                    "2️⃣ Configure SAT integration",
                                    "3️⃣ Set up tracking parameters",
                                    "4️⃣ Test connection",
                                    "5️⃣ Enable tracking",
                                    "6️⃣ Monitor performance"
                                ],
                                "tips": [
                                    "💡 Ensure GPS accuracy",
                                    "💡 Test thoroughly",
                                    "💡 Maintain equipment"
                                ]
                            },
                            "gps_setup": {
                                "title": "📍 GPS Setup",
                                "steps": [
                                    "1️⃣ Logistics Hub → Setup → Gps Setup",
                                    "2️⃣ Configure GPS devices",
                                    "3️⃣ Link to vehicles",
                                    "4️⃣ Set tracking frequency",
                                    "5️⃣ Test tracking",
                                    "6️⃣ Monitor coverage"
                                ],
                                "tips": [
                                    "💡 Ensure device functionality",
                                    "💡 Check signal strength",
                                    "💡 Update firmware"
                                ]
                            },
                            "employee_timesheet": {
                                "title": "⏱️ Employee Timesheet",
                                "steps": [
                                    "1️⃣ Logistics Hub → Setup → Employee Timesheet",
                                    "2️⃣ Track driver hours",
                                    "3️⃣ Log activities",
                                    "4️⃣ Calculate time",
                                    "5️⃣ Approve timesheets",
                                    "6️⃣ Export for payroll"
                                ],
                                "tips": [
                                    "💡 Track hours accurately",
                                    "💡 Monitor overtime",
                                    "💡 Ensure compliance"
                                ]
                            },
                            "vehicles_logistics": {
                                "title": "🚛 Vehicles",
                                "steps": [
                                    "1️⃣ Logistics Hub → Setup → Vehicles",
                                    "2️⃣ Add vehicle details",
                                    "3️⃣ Track maintenance",
                                    "4️⃣ Monitor fuel",
                                    "5️⃣ Schedule service",
                                    "6️⃣ Track costs"
                                ],
                                "tips": [
                                    "💡 Maintain vehicles",
                                    "💡 Track operating costs",
                                    "💡 Plan replacements"
                                ]
                            },
                            "channels_and_tiers": {
                                "title": "📊 Channels and Tiers",
                                "steps": [
                                    "1️⃣ Logistics Hub → Setup → Channels and Tiers",
                                    "2️⃣ Define distribution channels",
                                    "3️⃣ Set up customer tiers",
                                    "4️⃣ Assign priorities",
                                    "5️⃣ Configure service levels",
                                    "6️⃣ Monitor performance"
                                ],
                                "tips": [
                                    "💡 Align with strategy",
                                    "💡 Prioritize key customers",
                                    "💡 Review regularly"
                                ]
                            },
                            "survey": {
                                "title": "📝 Survey",
                                "steps": [
                                    "1️⃣ Logistics Hub → Setup → Survey",
                                    "2️⃣ Create satisfaction surveys",
                                    "3️⃣ Send to customers",
                                    "4️⃣ Collect responses",
                                    "5️⃣ Analyze feedback",
                                    "6️⃣ Improve service"
                                ],
                                "tips": [
                                    "💡 Keep surveys short",
                                    "💡 Act on feedback",
                                    "💡 Track trends"
                                ]
                            },
                            "distributors": {
                                "title": "🤝 Distributors",
                                "steps": [
                                    "1️⃣ Logistics Hub → Setup → Distributors",
                                    "2️⃣ Manage distributor network",
                                    "3️⃣ Track performance",
                                    "4️⃣ Monitor inventory",
                                    "5️⃣ Coordinate deliveries",
                                    "6️⃣ Evaluate partnerships"
                                ],
                                "tips": [
                                    "💡 Maintain relationships",
                                    "💡 Track metrics",
                                    "💡 Optimize network"
                                ]
                            }
                        }
                    },
                    "gps_and_maps": {
                        "title": "🗺️ GPS and Maps",
                        "sub_modules": {
                            "gps_locations": {
                                "title": "📍 GPS Locations",
                                "steps": [
                                    "1️⃣ Logistics Hub → Gps and Maps → Gps Locations",
                                    "2️⃣ View real-time locations",
                                    "3️⃣ Track vehicles",
                                    "4️⃣ Monitor routes",
                                    "5️⃣ Identify delays",
                                    "6️⃣ Optimize paths"
                                ],
                                "tips": [
                                    "💡 Monitor live",
                                    "💡 Respond to issues",
                                    "💡 Optimize routes"
                                ]
                            },
                            "customer_map": {
                                "title": "🗺️ Customer Map",
                                "steps": [
                                    "1️⃣ Logistics Hub → Gps and Maps → Customer Map",
                                    "2️⃣ View customer locations",
                                    "3️⃣ Plan routes",
                                    "4️⃣ Optimize deliveries",
                                    "5️⃣ Identify clusters",
                                    "6️⃣ Improve efficiency"
                                ],
                                "tips": [
                                    "💡 Use for planning",
                                    "💡 Group deliveries",
                                    "💡 Reduce travel time"
                                ]
                            }
                        }
                    },
                    "route_and_calls": {
                        "title": "🛣️ Route and Calls",
                        "sub_modules": {
                            "routes": {
                                "title": "🛣️ Routes",
                                "steps": [
                                    "1️⃣ Logistics Hub → Route and Calls → Routes",
                                    "2️⃣ Create delivery routes",
                                    "3️⃣ Assign customers",
                                    "4️⃣ Optimize sequence",
                                    "5️⃣ Schedule runs",
                                    "6️⃣ Track performance"
                                ],
                                "tips": [
                                    "💡 Optimize for efficiency",
                                    "💡 Balance workloads",
                                    "💡 Update regularly"
                                ]
                            },
                            "routes_assignments": {
                                "title": "📋 Routes Assignments",
                                "steps": [
                                    "1️⃣ Logistics Hub → Route and Calls → Routes Assignments",
                                    "2️⃣ Assign routes to drivers",
                                    "3️⃣ Set schedules",
                                    "4️⃣ Monitor completion",
                                    "5️⃣ Adjust as needed",
                                    "6️⃣ Track performance"
                                ],
                                "tips": [
                                    "💡 Match drivers to routes",
                                    "💡 Consider experience",
                                    "💡 Monitor results"
                                ]
                            },
                            "subjects_and_actions": {
                                "title": "📋 Subjects And Actions",
                                "steps": [
                                    "1️⃣ Logistics Hub → Route and Calls → Subjects And Actions",
                                    "2️⃣ Define call activities",
                                    "3️⃣ Set action types",
                                    "4️⃣ Track interactions",
                                    "5️⃣ Log results",
                                    "6️⃣ Analyze effectiveness"
                                ],
                                "tips": [
                                    "💡 Standardize activities",
                                    "💡 Track outcomes",
                                    "💡 Improve processes"
                                ]
                            },
                            "activity_status": {
                                "title": "✅ Activity Status",
                                "steps": [
                                    "1️⃣ Logistics Hub → Route and Calls → Activity Status",
                                    "2️⃣ Track call status",
                                    "3️⃣ Monitor completion",
                                    "4️⃣ Update progress",
                                    "5️⃣ Report results",
                                    "6️⃣ Plan follow-ups"
                                ],
                                "tips": [
                                    "💡 Track in real-time",
                                    "💡 Follow up promptly",
                                    "💡 Measure success"
                                ]
                            },
                            "call_management": {
                                "title": "📞 Call Management",
                                "steps": [
                                    "1️⃣ Logistics Hub → Route and Calls → Call Management",
                                    "2️⃣ Schedule customer calls",
                                    "3️⃣ Log call details",
                                    "4️⃣ Record outcomes",
                                    "5️⃣ Set follow-ups",
                                    "6️⃣ Analyze patterns"
                                ],
                                "tips": [
                                    "💡 Prepare before calls",
                                    "💡 Document thoroughly",
                                    "💡 Follow up consistently"
                                ]
                            }
                        }
                    },
                    "recurring_postings_logistics": {
                        "title": "🔄 Recurring Postings",
                        "sub_modules": {
                            "recurring_templates": {
                                "title": "📋 Recurring Templates",
                                "steps": [
                                    "1️⃣ Logistics Hub → Recurring Postings → Recurring Templates",
                                    "2️⃣ Create recurring schedules",
                                    "3️⃣ Set frequency",
                                    "4️⃣ Assign routes",
                                    "5️⃣ Generate automatically",
                                    "6️⃣ Monitor execution"
                                ],
                                "tips": [
                                    "💡 Automate regular runs",
                                    "💡 Review periodically",
                                    "💡 Adjust as needed"
                                ]
                            }
                        }
                    },
                    "dispatch_management": {
                        "title": "📦 Dispatch Management",
                        "sub_modules": {
                            "dashboard_dispatch": {
                                "title": "📊 Dashboard",
                                "steps": [
                                    "1️⃣ Logistics Hub → Dispatch Management → Dashboard",
                                    "2️⃣ View dispatch overview",
                                    "3️⃣ Monitor active dispatches",
                                    "4️⃣ Track completion",
                                    "5️⃣ Identify issues",
                                    "6️⃣ Optimize operations"
                                ],
                                "tips": [
                                    "💡 Monitor in real-time",
                                    "💡 Respond quickly",
                                    "💡 Improve efficiency"
                                ]
                            },
                            "dispatch": {
                                "title": "📦 Dispatch",
                                "steps": [
                                    "1️⃣ Logistics Hub → Dispatch Management → Dispatch",
                                    "2️⃣ Create dispatch orders",
                                    "3️⃣ Assign vehicles",
                                    "4️⃣ Schedule deliveries",
                                    "5️⃣ Track execution",
                                    "6️⃣ Confirm completion"
                                ],
                                "tips": [
                                    "💡 Plan efficiently",
                                    "💡 Monitor progress",
                                    "💡 Adjust as needed"
                                ]
                            }
                        }
                    },
                    "sales_targets": {
                        "title": "🎯 Sales Targets",
                        "sub_modules": {
                            "sales_targets_reports": {
                                "title": "📊 Sales Targets Reports",
                                "steps": [
                                    "1️⃣ Logistics Hub → Sales Targets → Sales Targets Reports",
                                    "2️⃣ Set sales targets",
                                    "3️⃣ Track achievement",
                                    "4️⃣ Analyze performance",
                                    "5️⃣ Identify gaps",
                                    "6️⃣ Adjust targets"
                                ],
                                "tips": [
                                    "💡 Set realistic targets",
                                    "💡 Monitor progress",
                                    "💡 Adjust as needed"
                                ]
                            }
                        }
                    }
                },
                "video_url": "https://training.leysco.com/videos/logistics",
                "doc_url": "https://docs.leysco.com/logistics-guide",
                "estimated_time": "50 minutes",
                "prerequisites": ["Logistics access rights"],
                "keywords": ["logistics", "route", "dispatch", "gps", "vehicle", "tracking"]
            },

            # =========================================================
            # 17. PRODUCTION OPERATIONS
            # =========================================================
            "production_operations": {
                "id": "production_operations",
                "title": "🏭 Production Operations",
                "description": "Complete production management including BOMs, orders, and costing",
                "sub_modules": {
                    "bill_of_materials": {
                        "title": "📋 Bill of Materials",
                        "steps": [
                            "1️⃣ Production → Bill of Materials",
                            "2️⃣ Create new BOM",
                            "3️⃣ Select finished product",
                            "4️⃣ Add components with quantities",
                            "5️⃣ Set labor and overhead",
                            "6️⃣ Save and validate"
                        ],
                        "tips": [
                            "💡 Keep BOMs accurate",
                            "💡 Update for changes",
                            "💡 Review regularly"
                        ]
                    },
                    "production_order": {
                        "title": "📑 Production Order",
                        "steps": [
                            "1️⃣ Production → Production Order",
                            "2️⃣ Create new order",
                            "3️⃣ Select product and BOM",
                            "4️⃣ Enter quantity",
                            "5️⃣ Set due date",
                            "6️⃣ Release to production"
                        ],
                        "tips": [
                            "💡 Plan realistically",
                            "💡 Monitor progress",
                            "💡 Handle rush orders"
                        ]
                    },
                    "receipt_from_production": {
                        "title": "📥 Receipt from Production",
                        "steps": [
                            "1️⃣ Production → Receipt from Production",
                            "2️⃣ Select production order",
                            "3️⃣ Enter finished quantity",
                            "4️⃣ Record scrap",
                            "5️⃣ Move to inventory",
                            "6️⃣ Complete order"
                        ],
                        "tips": [
                            "💡 Verify quality",
                            "💡 Track yield",
                            "💡 Update costs"
                        ]
                    },
                    "issue_for_production": {
                        "title": "📤 Issue for Production",
                        "steps": [
                            "1️⃣ Production → Issue for Production",
                            "2️⃣ Select production order",
                            "3️⃣ Issue components",
                            "4️⃣ Verify quantities",
                            "5️⃣ Record usage",
                            "6️⃣ Update inventory"
                        ],
                        "tips": [
                            "💡 Issue accurately",
                            "💡 Track variances",
                            "💡 Investigate differences"
                        ]
                    },
                    "procurement_confirmation_wizard": {
                        "title": "🔧 Procurement Confirmation Wizard",
                        "steps": [
                            "1️⃣ Production → Procurement Confirmation Wizard",
                            "2️⃣ Review MRP results",
                            "3️⃣ Select items to procure",
                            "4️⃣ Choose vendors",
                            "5️⃣ Generate purchase orders",
                            "6️⃣ Confirm procurement"
                        ],
                        "tips": [
                            "💡 Review recommendations",
                            "💡 Verify quantities",
                            "💡 Place orders timely"
                        ]
                    },
                    "production_quality_check": {
                        "title": "✓ Production Quality Check",
                        "steps": [
                            "1️⃣ Production → Production Quality Check",
                            "2️⃣ Schedule quality checks",
                            "3️⃣ Test samples",
                            "4️⃣ Record results",
                            "5️⃣ Approve/reject",
                            "6️⃣ Document findings"
                        ],
                        "tips": [
                            "💡 Maintain quality standards",
                            "💡 Track defects",
                            "💡 Improve processes"
                        ]
                    },
                    "update_parent_item_prices_globally": {
                        "title": "💰 Update Parent Item Prices Globally",
                        "steps": [
                            "1️⃣ Production → Update Parent Item Prices Globally",
                            "2️⃣ Select parent items",
                            "3️⃣ Calculate from components",
                            "4️⃣ Review price changes",
                            "5️⃣ Apply updates",
                            "6️⃣ Verify results"
                        ],
                        "tips": [
                            "💡 Keep prices current",
                            "💡 Review impact",
                            "💡 Update regularly"
                        ]
                    },
                    "production_cost_recalculation_wizard": {
                        "title": "📊 Production Cost Recalculation Wizard",
                        "steps": [
                            "1️⃣ Production → Production Cost Recalculation Wizard",
                            "2️⃣ Select orders",
                            "3️⃣ Recalculate costs",
                            "4️⃣ Review variances",
                            "5️⃣ Update costs",
                            "6️⃣ Analyze results"
                        ],
                        "tips": [
                            "💡 Reconcile costs",
                            "💡 Identify issues",
                            "💡 Improve accuracy"
                        ]
                    },
                    "bill_of_materials_component_management": {
                        "title": "🔄 Bill of Materials - Component Management",
                        "steps": [
                            "1️⃣ Production → Bill of Materials - Component Management",
                            "2️⃣ Select component",
                            "3️⃣ View all BOMs using it",
                            "4️⃣ Make changes",
                            "5️⃣ Update all BOMs",
                            "6️⃣ Verify changes"
                        ],
                        "tips": [
                            "💡 Manage changes centrally",
                            "💡 Document reasons",
                            "💡 Notify users"
                        ]
                    },
                    "production_std_cost_management": {
                        "title": "📊 Production Std Cost Management",
                        "steps": [
                            "1️⃣ Production → Production Std Cost Management",
                            "2️⃣ Set standard costs",
                            "3️⃣ Update periodically",
                            "4️⃣ Review variances",
                            "5️⃣ Adjust standards",
                            "6️⃣ Monitor accuracy"
                        ],
                        "tips": [
                            "💡 Set realistic standards",
                            "💡 Review regularly",
                            "💡 Investigate variances"
                        ]
                    },
                    "production_std_cost_rollup": {
                        "title": "📈 Production Std Cost Rollup",
                        "steps": [
                            "1️⃣ Production → Production Std Cost Rollup",
                            "2️⃣ Roll up component costs",
                            "3️⃣ Calculate parent costs",
                            "4️⃣ Review results",
                            "5️⃣ Update standards",
                            "6️⃣ Verify calculations"
                        ],
                        "tips": [
                            "💡 Ensure accuracy",
                            "💡 Check logic",
                            "💡 Update regularly"
                        ]
                    },
                    "production_std_cost_update": {
                        "title": "🔄 Production Std Cost Update",
                        "steps": [
                            "1️⃣ Production → Production Std Cost Update",
                            "2️⃣ Select items to update",
                            "3️⃣ Apply new standards",
                            "4️⃣ Review changes",
                            "5️⃣ Confirm updates",
                            "6️⃣ Document changes"
                        ],
                        "tips": [
                            "💡 Update systematically",
                            "💡 Review impact",
                            "💡 Communicate changes"
                        ]
                    },
                    "production_reports": {
                        "title": "📊 Production Reports",
                        "sub_modules": {
                            "electronic_reports": {
                                "title": "📄 Electronic Reports",
                                "steps": [
                                    "1️⃣ Production → Production Reports → Electronic Reports",
                                    "2️⃣ Select report type",
                                    "3️⃣ Set parameters",
                                    "4️⃣ Generate report",
                                    "5️⃣ Export if needed",
                                    "6️⃣ Analyze results"
                                ],
                                "tips": [
                                    "💡 Use for analysis",
                                    "💡 Schedule regularly",
                                    "💡 Share with team"
                                ]
                            },
                            "production_order_status": {
                                "title": "📋 Production Order Status",
                                "steps": [
                                    "1️⃣ Production → Production Reports → Production Order Status",
                                    "2️⃣ View all orders",
                                    "3️⃣ Check status",
                                    "4️⃣ Identify delays",
                                    "5️⃣ Monitor progress",
                                    "6️⃣ Update priorities"
                                ],
                                "tips": [
                                    "💡 Monitor daily",
                                    "💡 Address delays",
                                    "💡 Adjust schedules"
                                ]
                            },
                            "bill_of_materials_report": {
                                "title": "📋 Bill of Materials Report",
                                "steps": [
                                    "1️⃣ Production → Production Reports → Bill of Materials Report",
                                    "2️⃣ Select BOMs",
                                    "3️⃣ Generate report",
                                    "4️⃣ Review components",
                                    "5️⃣ Verify accuracy",
                                    "6️⃣ Export for reference"
                                ],
                                "tips": [
                                    "💡 Keep BOMs current",
                                    "💡 Review periodically",
                                    "💡 Use for costing"
                                ]
                            },
                            "open_items_list": {
                                "title": "📋 Open Items List",
                                "steps": [
                                    "1️⃣ Production → Production Reports → Open Items List",
                                    "2️⃣ View open production items",
                                    "3️⃣ Check status",
                                    "4️⃣ Identify bottlenecks",
                                    "5️⃣ Prioritize work",
                                    "6️⃣ Update schedules"
                                ],
                                "tips": [
                                    "💡 Review daily",
                                    "💡 Address bottlenecks",
                                    "💡 Keep items moving"
                                ]
                            },
                            "material_requirements_mrp": {
                                "title": "📦 Material Requirements (MRP)",
                                "steps": [
                                    "1️⃣ Production → Production Reports → Material Requirements (MRP)",
                                    "2️⃣ Run MRP",
                                    "3️⃣ Review requirements",
                                    "4️⃣ Plan procurement",
                                    "5️⃣ Generate suggestions",
                                    "6️⃣ Place orders"
                                ],
                                "tips": [
                                    "💡 Run regularly",
                                    "💡 Plan ahead",
                                    "💡 Avoid shortages"
                                ]
                            },
                            "production_variance_report_agri_v2": {
                                "title": "📊 Production Variance Report Agri V2",
                                "steps": [
                                    "1️⃣ Production → Production Reports → Production Variance Report Agri V2",
                                    "2️⃣ Select period",
                                    "3️⃣ Review variances",
                                    "4️⃣ Investigate causes",
                                    "5️⃣ Take corrective action",
                                    "6️⃣ Update standards"
                                ],
                                "tips": [
                                    "💡 Investigate variances",
                                    "💡 Identify trends",
                                    "💡 Improve processes"
                                ]
                            },
                            "issue_tracking_report": {
                                "title": "🔍 Issue Tracking Report",
                                "steps": [
                                    "1️⃣ Production → Production Reports → Issue Tracking Report",
                                    "2️⃣ Track production issues",
                                    "3️⃣ Monitor resolution",
                                    "4️⃣ Identify patterns",
                                    "5️⃣ Implement fixes",
                                    "6️⃣ Prevent recurrence"
                                ],
                                "tips": [
                                    "💡 Track all issues",
                                    "💡 Resolve quickly",
                                    "💡 Learn from problems"
                                ]
                            },
                            "production_completion": {
                                "title": "✅ Production Completion",
                                "steps": [
                                    "1️⃣ Production → Production Reports → Production Completion",
                                    "2️⃣ Track completed orders",
                                    "3️⃣ Review performance",
                                    "4️⃣ Calculate metrics",
                                    "5️⃣ Celebrate success",
                                    "6️⃣ Plan improvements"
                                ],
                                "tips": [
                                    "💡 Monitor completion rates",
                                    "💡 Recognize achievements",
                                    "💡 Improve efficiency"
                                ]
                            },
                            "wip_variance_report": {
                                "title": "📊 WIP Variance Report",
                                "steps": [
                                    "1️⃣ Production → Production Reports → WIP Variance Report",
                                    "2️⃣ Review WIP variances",
                                    "3️⃣ Investigate causes",
                                    "4️⃣ Adjust WIP values",
                                    "5️⃣ Update costs",
                                    "6️⃣ Improve accuracy"
                                ],
                                "tips": [
                                    "💡 Monitor WIP closely",
                                    "💡 Investigate variances",
                                    "💡 Maintain accuracy"
                                ]
                            }
                        }
                    }
                },
                "video_url": "https://training.leysco.com/videos/production",
                "doc_url": "https://docs.leysco.com/production-guide",
                "estimated_time": "60 minutes",
                "prerequisites": ["Production access rights"],
                "keywords": ["production", "bom", "manufacturing", "order", "cost", "mrp"]
            },

            # =========================================================
            # 18. GATE PASS MANAGEMENT
            # =========================================================
            "gate_pass_mgt": {
                "id": "gate_pass_mgt",
                "title": "🚪 Gate Pass Management",
                "description": "Complete gate pass, security, and vehicle movement control",
                "sub_modules": {
                    "users_gate": {
                        "title": "👥 Users",
                        "steps": [
                            "1️⃣ Gate Pass Mgt → Users",
                            "2️⃣ Manage gate users",
                            "3️⃣ Set permissions",
                            "4️⃣ Assign roles",
                            "5️⃣ Monitor activity",
                            "6️⃣ Update as needed"
                        ],
                        "tips": [
                            "💡 Control access",
                            "💡 Train users",
                            "💡 Review regularly"
                        ]
                    },
                    "gpm_dashboard": {
                        "title": "📊 Gpm Dashboard",
                        "steps": [
                            "1️⃣ Gate Pass Mgt → Gpm Dashboard",
                            "2️⃣ View gate activity",
                            "3️⃣ Monitor movements",
                            "4️⃣ Check pending passes",
                            "5️⃣ Review alerts",
                            "6️⃣ Track metrics"
                        ],
                        "tips": [
                            "💡 Monitor in real-time",
                            "💡 Respond to alerts",
                            "💡 Review daily"
                        ]
                    },
                    "documents_gate": {
                        "title": "📄 Documents",
                        "steps": [
                            "1️⃣ Gate Pass Mgt → Documents",
                            "2️⃣ Create gate passes",
                            "3️⃣ Link to deliveries",
                            "4️⃣ Print passes",
                            "5️⃣ Track document status",
                            "6️⃣ Archive completed"
                        ],
                        "tips": [
                            "💡 Use templates",
                            "💡 Include all details",
                            "💡 Maintain records"
                        ]
                    },
                    "scan_logs": {
                        "title": "📱 Scan Logs",
                        "steps": [
                            "1️⃣ Gate Pass Mgt → Scan Logs",
                            "2️⃣ View scan history",
                            "3️⃣ Track check-ins/outs",
                            "4️⃣ Monitor gate activity",
                            "5️⃣ Investigate anomalies",
                            "6️⃣ Generate reports"
                        ],
                        "tips": [
                            "💡 Review regularly",
                            "💡 Investigate discrepancies",
                            "💡 Maintain logs"
                        ]
                    },
                    "backup_mode": {
                        "title": "💾 Backup Mode",
                        "steps": [
                            "1️⃣ Gate Pass Mgt → Backup Mode",
                            "2️⃣ Enable backup mode",
                            "3️⃣ Continue operations offline",
                            "4️⃣ Sync when connected",
                            "5️⃣ Verify data integrity",
                            "6️⃣ Disable when done"
                        ],
                        "tips": [
                            "💡 Use during outages",
                            "💡 Test regularly",
                            "💡 Sync promptly"
                        ]
                    },
                    "gpm_settings": {
                        "title": "⚙️ Gpm Settings",
                        "sub_modules": {
                            "settings_gate": {
                                "title": "⚙️ Settings",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Gpm Settings → Settings",
                                    "2️⃣ Configure gate parameters",
                                    "3️⃣ Set business rules",
                                    "4️⃣ Define workflows",
                                    "5️⃣ Test settings",
                                    "6️⃣ Monitor effectiveness"
                                ],
                                "tips": [
                                    "💡 Optimize settings",
                                    "💡 Test changes",
                                    "💡 Review periodically"
                                ]
                            },
                            "gates": {
                                "title": "🚪 Gates",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Gpm Settings → Gates",
                                    "2️⃣ Define gates",
                                    "3️⃣ Set gate types",
                                    "4️⃣ Assign guards",
                                    "5️⃣ Configure equipment",
                                    "6️⃣ Monitor operations"
                                ],
                                "tips": [
                                    "💡 Organize by location",
                                    "💡 Assign responsibility",
                                    "💡 Maintain equipment"
                                ]
                            },
                            "backup_mode_settings": {
                                "title": "💾 Backup Mode",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Gpm Settings → Backup Mode",
                                    "2️⃣ Configure backup settings",
                                    "3️⃣ Set sync frequency",
                                    "4️⃣ Define data retention",
                                    "5️⃣ Test backup",
                                    "6️⃣ Monitor status"
                                ],
                                "tips": [
                                    "💡 Ensure data safety",
                                    "💡 Test recovery",
                                    "💡 Monitor backups"
                                ]
                            },
                            "setting": {
                                "title": "⚙️ Setting",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Gpm Settings → Setting",
                                    "2️⃣ Configure general settings",
                                    "3️⃣ Set preferences",
                                    "4️⃣ Define defaults",
                                    "5️⃣ Save configuration",
                                    "6️⃣ Verify settings"
                                ],
                                "tips": [
                                    "💡 Optimize for efficiency",
                                    "💡 Document changes",
                                    "💡 Review regularly"
                                ]
                            },
                            "mobile_settings": {
                                "title": "📱 Mobile Settings",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Gpm Settings → Mobile Settings",
                                    "2️⃣ Configure mobile access",
                                    "3️⃣ Set app permissions",
                                    "4️⃣ Define offline behavior",
                                    "5️⃣ Test mobile features",
                                    "6️⃣ Monitor usage"
                                ],
                                "tips": [
                                    "💡 Enable field access",
                                    "💡 Ensure security",
                                    "💡 Test thoroughly"
                                ]
                            },
                            "form_fields": {
                                "title": "📋 Form Fields",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Gpm Settings → Form Fields",
                                    "2️⃣ Customize gate pass forms",
                                    "3️⃣ Add required fields",
                                    "4️⃣ Set field properties",
                                    "5️⃣ Test forms",
                                    "6️⃣ Update as needed"
                                ],
                                "tips": [
                                    "💡 Capture all needed data",
                                    "💡 Keep forms simple",
                                    "💡 Review periodically"
                                ]
                            },
                            "form_fields_templates": {
                                "title": "📋 Form Fields Templates",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Gpm Settings → Form Fields Templates",
                                    "2️⃣ Create form templates",
                                    "3️⃣ Apply to gate types",
                                    "4️⃣ Standardize data collection",
                                    "5️⃣ Test templates",
                                    "6️⃣ Update as needed"
                                ],
                                "tips": [
                                    "💡 Standardize processes",
                                    "💡 Ensure consistency",
                                    "💡 Train users"
                                ]
                            },
                            "mobile_menu": {
                                "title": "📱 Mobile Menu",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Gpm Settings → Mobile Menu",
                                    "2️⃣ Configure mobile navigation",
                                    "3️⃣ Set menu items",
                                    "4️⃣ Organize for efficiency",
                                    "5️⃣ Test on devices",
                                    "6️⃣ Update as needed"
                                ],
                                "tips": [
                                    "💡 Optimize for mobile",
                                    "💡 Keep simple",
                                    "💡 Test thoroughly"
                                ]
                            }
                        }
                    },
                    "reports_gate": {
                        "title": "📊 Reports",
                        "sub_modules": {
                            "scanlogs_report": {
                                "title": "📱 Scanlogs Report",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Reports → Scanlogs Report",
                                    "2️⃣ Select date range",
                                    "3️⃣ Generate report",
                                    "4️⃣ Review activity",
                                    "5️⃣ Export for analysis",
                                    "6️⃣ Share with management"
                                ],
                                "tips": [
                                    "💡 Review regularly",
                                    "💡 Identify patterns",
                                    "💡 Improve security"
                                ]
                            },
                            "duplicate_logs_report": {
                                "title": "🔄 Duplicate logs Report",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Reports → Duplicate logs Report",
                                    "2️⃣ Identify duplicates",
                                    "3️⃣ Investigate causes",
                                    "4️⃣ Resolve issues",
                                    "5️⃣ Clean up data",
                                    "6️⃣ Prevent recurrence"
                                ],
                                "tips": [
                                    "💡 Investigate duplicates",
                                    "💡 Fix root causes",
                                    "💡 Maintain data quality"
                                ]
                            },
                            "does_not_exist_report": {
                                "title": "❌ Does-not Exist Report",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Reports → Does-not Exist Report",
                                    "2️⃣ Find missing records",
                                    "3️⃣ Investigate gaps",
                                    "4️⃣ Update records",
                                    "5️⃣ Fix processes",
                                    "6️⃣ Verify completeness"
                                ],
                                "tips": [
                                    "💡 Ensure data integrity",
                                    "💡 Investigate gaps",
                                    "💡 Improve processes"
                                ]
                            },
                            "document_report": {
                                "title": "📄 Document Report",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Reports → Document Report",
                                    "2️⃣ Select document type",
                                    "3️⃣ Generate report",
                                    "4️⃣ Review documents",
                                    "5️⃣ Export as needed",
                                    "6️⃣ Archive for records"
                                ],
                                "tips": [
                                    "💡 Maintain records",
                                    "💡 Use for audits",
                                    "💡 Review periodically"
                                ]
                            },
                            "backup_mode_reports": {
                                "title": "💾 Backup Mode Reports",
                                "steps": [
                                    "1️⃣ Gate Pass Mgt → Reports → Backup Mode Reports",
                                    "2️⃣ Review backup status",
                                    "3️⃣ Check data integrity",
                                    "4️⃣ Verify sync completion",
                                    "5️⃣ Generate backup reports",
                                    "6️⃣ Ensure data safety"
                                ],
                                "tips": [
                                    "💡 Monitor backups",
                                    "💡 Test recovery",
                                    "💡 Maintain data"
                                ]
                            }
                        }
                    }
                },
                "video_url": "https://training.leysco.com/videos/gatepass",
                "doc_url": "https://docs.leysco.com/gatepass-guide",
                "estimated_time": "40 minutes",
                "prerequisites": ["Security/Supervisor access"],
                "keywords": ["gate", "security", "vehicle", "movement", "scan", "pass"]
            },

            # =========================================================
            # 19. DASHBOARD & ANALYTICS
            # =========================================================
            "dashboard": {
                "id": "dashboard",
                "title": "📊 Dashboard & Analytics",
                "description": "Real-time business intelligence and performance monitoring",
                "sub_modules": {
                    "dashboard_overview": {
                        "title": "📈 Dashboard Overview",
                        "steps": [
                            "1️⃣ Home → Dashboard",
                            "2️⃣ Review total sales and revenue",
                            "3️⃣ Check order count and new customers",
                            "4️⃣ Monitor key metrics",
                            "5️⃣ Identify trends",
                            "6️⃣ Take action on insights"
                        ],
                        "tips": [
                            "💡 Review daily",
                            "💡 Track KPIs",
                            "💡 Respond to changes"
                        ]
                    },
                    "sales_trends": {
                        "title": "📈 Sales Trends",
                        "steps": [
                            "1️⃣ Dashboard → Sales Trends",
                            "2️⃣ View daily/weekly/monthly trends",
                            "3️⃣ Compare periods",
                            "4️⃣ Analyze patterns",
                            "5️⃣ Forecast future",
                            "6️⃣ Plan accordingly"
                        ],
                        "tips": [
                            "💡 Monitor regularly",
                            "💡 Identify seasonality",
                            "💡 Adjust strategy"
                        ]
                    },
                    "revenue_by_product": {
                        "title": "💰 Revenue by Product",
                        "steps": [
                            "1️⃣ Dashboard → Revenue by Product",
                            "2️⃣ View top products",
                            "3️⃣ Analyze contribution",
                            "4️⃣ Identify best sellers",
                            "5️⃣ Plan inventory",
                            "6️⃣ Promote winners"
                        ],
                        "tips": [
                            "💡 Keep top sellers stocked",
                            "💡 Promote slow movers",
                            "💡 Optimize product mix"
                        ]
                    },
                    "top_buying_customers": {
                        "title": "👥 Top Buying Customers",
                        "steps": [
                            "1️⃣ Dashboard → Top Buying Customers",
                            "2️⃣ View key accounts",
                            "3️⃣ Analyze spending",
                            "4️⃣ Nurture relationships",
                            "5️⃣ Identify opportunities",
                            "6️⃣ Grow accounts"
                        ],
                        "tips": [
                            "💡 Focus on top customers",
                            "💡 Understand their needs",
                            "💡 Build relationships"
                        ]
                    },
                    "business_intelligence": {
                        "title": "📊 Business Intelligence",
                        "steps": [
                            "1️⃣ Dashboard → Business Intelligence",
                            "2️⃣ Review key ratios",
                            "3️⃣ Monitor gross margin",
                            "4️⃣ Check credit ratio",
                            "5️⃣ Analyze avg order",
                            "6️⃣ Track per customer metrics"
                        ],
                        "tips": [
                            "💡 Track trends",
                            "💡 Investigate changes",
                            "💡 Improve performance"
                        ]
                    },
                    "business_insights": {
                        "title": "💡 Business Insights",
                        "steps": [
                            "1️⃣ Dashboard → Business Insights",
                            "2️⃣ Review automated insights",
                            "3️⃣ Identify risks",
                            "4️⃣ Spot opportunities",
                            "5️⃣ Take action",
                            "6️⃣ Monitor results"
                        ],
                        "tips": [
                            "💡 Act on insights",
                            "💡 Diversify customer base",
                            "💡 Address risks"
                        ]
                    },
                    "top_selling_product": {
                        "title": "🏆 Top Selling Product",
                        "steps": [
                            "1️⃣ Dashboard → Top Selling Product",
                            "2️⃣ View best performer",
                            "3️⃣ Analyze sales",
                            "4️⃣ Ensure stock",
                            "5️⃣ Plan promotions",
                            "6️⃣ Replicate success"
                        ],
                        "tips": [
                            "💡 Never run out",
                            "💡 Feature prominently",
                            "💡 Learn from success"
                        ]
                    },
                    "performance_analytics": {
                        "title": "📊 Performance Analytics",
                        "sub_modules": {
                            "branch_performance": {
                                "title": "🏢 Branch Performance",
                                "steps": [
                                    "1️⃣ Dashboard → Performance Analytics → Branch Performance",
                                    "2️⃣ Compare branches",
                                    "3️⃣ Identify top performers",
                                    "4️⃣ Address underperformers",
                                    "5️⃣ Share best practices",
                                    "6️⃣ Set targets"
                                ],
                                "tips": [
                                    "💡 Recognize top branches",
                                    "💡 Support others",
                                    "💡 Share success"
                                ]
                            },
                            "sales_leaderboard": {
                                "title": "🏆 Sales Leaderboard",
                                "steps": [
                                    "1️⃣ Dashboard → Performance Analytics → Sales Leaderboard",
                                    "2️⃣ View sales rankings",
                                    "3️⃣ Recognize top performers",
                                    "4️⃣ Motivate team",
                                    "5️⃣ Set goals",
                                    "6️⃣ Track progress"
                                ],
                                "tips": [
                                    "💡 Celebrate wins",
                                    "💡 Encourage competition",
                                    "💡 Support development"
                                ]
                            }
                        }
                    },
                    "slow_moving_items": {
                        "title": "🐢 Slow Moving Items",
                        "steps": [
                            "1️⃣ Dashboard → Slow Moving",
                            "2️⃣ Identify slow movers",
                            "3️⃣ Review critical items",
                            "4️⃣ Plan promotions",
                            "5️⃣ Consider clearance",
                            "6️⃣ Adjust ordering"
                        ],
                        "tips": [
                            "💡 Address slow movers",
                            "💡 Free up cash",
                            "💡 Make room for winners"
                        ]
                    },
                    "inactive_customers": {
                        "title": "💤 Inactive Customers",
                        "steps": [
                            "1️⃣ Dashboard → Inactive Customers",
                            "2️⃣ Identify inactive accounts",
                            "3️⃣ Re-engagement opportunities",
                            "4️⃣ Plan outreach",
                            "5️⃣ Win back customers",
                            "6️⃣ Track success"
                        ],
                        "tips": [
                            "💡 Re-engage inactive",
                            "💡 Offer incentives",
                            "💡 Understand why"
                        ]
                    }
                },
                "video_url": "https://training.leysco.com/videos/dashboard",
                "doc_url": "https://docs.leysco.com/dashboard-guide",
                "estimated_time": "30 minutes",
                "prerequisites": ["Dashboard access"],
                "keywords": ["dashboard", "analytics", "kpi", "metrics", "insights", "performance"]
            }
        }

        # =========================================================
        # VIDEO TUTORIALS LIBRARY
        # =========================================================
        self.training_videos = {
            "administration": "https://training.leysco.com/videos/administration",
            "financials": "https://training.leysco.com/videos/financials",
            "banking_master": "https://training.leysco.com/videos/banking-master",
            "inventory_master": "https://training.leysco.com/videos/inventory-master",
            "production_master": "https://training.leysco.com/videos/production-master",
            "resources_master": "https://training.leysco.com/videos/resources-master",
            "service": "https://training.leysco.com/videos/service",
            "data_imports": "https://training.leysco.com/videos/data-imports",
            "utilities": "https://training.leysco.com/videos/utilities",
            "sales": "https://training.leysco.com/videos/sales",
            "purchase": "https://training.leysco.com/videos/purchase",
            "bp": "https://training.leysco.com/videos/business-partners",
            "banking_transactions": "https://training.leysco.com/videos/banking-transactions",
            "inventory_transactions": "https://training.leysco.com/videos/inventory-transactions",
            "resources": "https://training.leysco.com/videos/resources",
            "logistics": "https://training.leysco.com/videos/logistics",
            "production": "https://training.leysco.com/videos/production",
            "gatepass": "https://training.leysco.com/videos/gatepass",
            "dashboard": "https://training.leysco.com/videos/dashboard"
        }

        # =========================================================
        # FAQ DATABASE
        # =========================================================
        self.faqs = {
            "administration": [
                {"q": "How do I add a new user?", "a": "Go to Administration → Setup → Users, click 'Add New User', enter details and assign permissions."},
                {"q": "How do I set up document numbering?", "a": "Go to Administration → System Initialization → Document Numbering, select document type and define format."},
                {"q": "How do I configure approval workflows?", "a": "Go to Utilities → Approval Process → Approval Stages to create stages, then Approval Templates to assign them."}
            ],
            "sales": [
                {"q": "How do I create a quotation?", "a": "Go to Sales → Quotations → New, select customer, add items, set validity, and save."},
                {"q": "How do I convert a quote to an order?", "a": "Open the quotation and click 'Copy To' → Sales Order."},
                {"q": "How do I create an invoice from delivery?", "a": "Open the delivery and click 'Copy To' → A/R Invoice."}
            ],
            "purchase": [
                {"q": "How do I create a purchase order?", "a": "Go to Purchase -A/P → Purchase Order → New, select vendor, add items, confirm prices."},
                {"q": "How do I receive goods against a PO?", "a": "Open the PO and click 'Copy To' → Goods Receipt PO."},
                {"q": "How do I process vendor invoices?", "a": "Go to Purchase -A/P → A/P Invoice → New, link to goods receipt, verify details, and post."}
            ],
            "inventory": [
                {"q": "How do I add a new item?", "a": "Go to Inventory → Item Management → Item Master data, click New, enter all details."},
                {"q": "How do I transfer stock between warehouses?", "a": "Go to Inventory → Inventory Transactions → Inventory Transfer, select from/to warehouses and items."},
                {"q": "How do I count inventory?", "a": "Go to Inventory → Inventory Transactions → Inventory Counting, create counting session, enter counts."}
            ],
            "banking": [
                {"q": "How do I record a customer payment?", "a": "Go to Banking → Incoming Payments, select customer, apply payment to invoices."},
                {"q": "How do I reconcile bank statements?", "a": "Go to Banking → Bank Statements and Ext Reconciliation → Reconciliation, match transactions."},
                {"q": "How do I make a vendor payment?", "a": "Go to Banking → Outgoing Payments, select vendor, choose invoices to pay."}
            ],
            "production": [
                {"q": "How do I create a bill of materials?", "a": "Go to Production → Bill of Materials, create new BOM with finished product and components."},
                {"q": "How do I create a production order?", "a": "Go to Production → Production Order, select product and BOM, enter quantity, release."},
                {"q": "How do I receive finished goods?", "a": "Go to Production → Receipt from Production, select order, enter finished quantity."}
            ],
            "logistics": [
                {"q": "How do I create a delivery route?", "a": "Go to Logistics Hub → Route and Calls → Routes, create new route and assign customers."},
                {"q": "How do I track vehicles?", "a": "Go to Logistics Hub → GPS and Maps → GPS Locations to view real-time tracking."},
                {"q": "How do I manage dispatches?", "a": "Go to Logistics Hub → Dispatch Management → Dispatch to create and track dispatches."}
            ],
            "gatepass": [
                {"q": "How do I create a gate pass?", "a": "Go to Gate Pass Mgt → Documents → New, link to delivery, enter vehicle details."},
                {"q": "How do I check vehicles in/out?", "a": "Use the scanning feature in Gate Pass Mgt → Scan Logs to record movements."},
                {"q": "How do I run gate pass reports?", "a": "Go to Gate Pass Mgt → Reports and select the required report type."}
            ],
            "dashboard": [
                {"q": "What does the dashboard show?", "a": "The dashboard shows real-time sales, revenue, orders, top products, customer insights, and key performance metrics."},
                {"q": "How do I view sales trends?", "a": "On the dashboard, scroll to Sales Trends section and select daily/weekly/monthly view."},
                {"q": "How do I identify slow-moving items?", "a": "Check the Slow Moving Items section on the dashboard for items with low turnover."}
            ]
        }

        # =========================================================
        # GLOSSARY OF TERMS
        # =========================================================
        self.glossary = {
            "BOM": "📋 **Bill of Materials** - List of components needed to manufacture a product",
            "MRP": "📦 **Material Requirements Planning** - System for planning manufacturing and purchasing",
            "PO": "📑 **Purchase Order** - Official order document sent to a supplier",
            "SO": "📋 **Sales Order** - Customer order confirmation document",
            "GRN": "📥 **Goods Receipt Note** - Document confirming receipt of goods",
            "DN": "📤 **Delivery Note** - Document accompanying shipped goods",
            "RMA": "↩️ **Return Material Authorization** - Authorization to return goods",
            "SKU": "🔖 **Stock Keeping Unit** - Unique identifier for each product",
            "UoM": "⚖️ **Unit of Measure** - Unit in which items are measured (pieces, kg, liters)",
            "EOQ": "📊 **Economic Order Quantity** - Optimal order quantity minimizing costs",
            "MOQ": "📏 **Minimum Order Quantity** - Smallest amount you can order",
            "ETA": "⏰ **Estimated Time of Arrival** - When delivery is expected",
            "AR": "💰 **Accounts Receivable** - Money owed by customers",
            "AP": "💳 **Accounts Payable** - Money owed to vendors",
            "GL": "📊 **General Ledger** - Main accounting records",
            "COGS": "📉 **Cost of Goods Sold** - Direct costs of producing goods sold",
            "WIP": "🏭 **Work in Progress** - Partially completed goods",
            "FIFO": "🔄 **First In, First Out** - Inventory valuation method",
            "LIFO": "🔄 **Last In, First Out** - Inventory valuation method",
            "CRM": "👥 **Customer Relationship Management** - Managing customer interactions",
            "KPI": "📈 **Key Performance Indicator** - Measurable value showing effectiveness",
            "BI": "📊 **Business Intelligence** - Data analysis for business insights",
            "RFQ": "❓ **Request for Quotation** - Request to suppliers for pricing",
            "RFP": "📄 **Request for Proposal** - Request for project proposals",
            "SLA": "🤝 **Service Level Agreement** - Contract defining service standards",
            "VAT": "🧾 **Value Added Tax** - Consumption tax on goods and services",
            "PIN": "🔑 **Personal Identification Number** - Tax registration number",
            "EDI": "💻 **Electronic Data Interchange** - Electronic document exchange",
            "API": "🔌 **Application Programming Interface** - Software integration interface",
            "ERP": "🏢 **Enterprise Resource Planning** - Integrated management system"
        }

        # =========================================================
        # WEBINAR SCHEDULE
        # =========================================================
        self.webinars = [
            {
                "topic": "🚀 Leysco100 Introduction & Navigation",
                "date": "2026-03-15",
                "time": "10:00 AM EAT",
                "duration": "60 min",
                "instructor": "Training Team"
            },
            {
                "topic": "💰 Financials Mastery",
                "date": "2026-03-18",
                "time": "2:00 PM EAT",
                "duration": "90 min",
                "instructor": "Finance Team"
            },
            {
                "topic": "📦 Inventory Management Best Practices",
                "date": "2026-03-22",
                "time": "11:00 AM EAT",
                "duration": "75 min",
                "instructor": "Operations Team"
            },
            {
                "topic": "💼 Sales Order Processing",
                "date": "2026-03-25",
                "time": "10:00 AM EAT",
                "duration": "60 min",
                "instructor": "Sales Team"
            },
            {
                "topic": "🏭 Production Planning & MRP",
                "date": "2026-03-29",
                "time": "2:00 PM EAT",
                "duration": "90 min",
                "instructor": "Production Team"
            },
            {
                "topic": "🚚 Logistics & Dispatch Management",
                "date": "2026-04-01",
                "time": "11:00 AM EAT",
                "duration": "75 min",
                "instructor": "Logistics Team"
            },
            {
                "topic": "📊 Dashboard & Analytics Deep Dive",
                "date": "2026-04-05",
                "time": "10:00 AM EAT",
                "duration": "60 min",
                "instructor": "BI Team"
            },
            {
                "topic": "🔐 Security & Gate Pass Management",
                "date": "2026-04-08",
                "time": "2:00 PM EAT",
                "duration": "45 min",
                "instructor": "Security Team"
            }
        ]

    # =========================================================
    # MAIN HANDLER METHODS - FIXED WITH LANGUAGE PARAMETER
    # =========================================================

    def handle_training_module(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle general training requests"""
        text = message.lower() if message else ''
        
        # Check if asking for specific module
        for module_id, module in self.training_modules.items():
            if module_id in text or module["title"].lower() in text:
                return self._format_module_response(module_id, module)
        
        # Check if asking for specific sub-module
        for module_id, module in self.training_modules.items():
            for sub_id, sub_module in module.get("sub_modules", {}).items():
                if sub_id in text or sub_module["title"].lower() in text:
                    return self._format_submodule_response(module_id, sub_id, module, sub_module)
        
        # If no specific module, show all available
        return self._show_all_modules()

    def handle_training_video(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle video tutorial requests"""
        text = message.lower() if message else ''
        
        for topic, url in self.training_videos.items():
            if topic in text:
                topic_name = topic.replace("_", " ").title()
                return f"🎥 **{topic_name} Video Tutorial**\n\nWatch now: {url}\n\n📚 Related modules: {self._get_related_modules(topic)}"
        
        return self._list_all_videos()

    def handle_training_guide(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle documentation requests"""
        text = message.lower() if message else ''
        
        for module_id, module in self.training_modules.items():
            if module_id in text or module["title"].lower() in text:
                return f"📄 **{module['title']} Documentation**\n\nAccess the full guide: {module['doc_url']}\n\n{module['description']}"
        
        return "📚 **All Documentation**\n\nAccess all guides at: https://docs.leysco.com"

    def handle_training_faq(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle FAQ requests"""
        text = message.lower() if message else ''
        
        for category, faqs in self.faqs.items():
            if category in text:
                return self._format_faq_response(category, faqs)
        
        return self._show_faq_menu()

    def handle_training_glossary(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle glossary/term definition requests"""
        text = message.lower() if message else ''
        
        for term, definition in self.glossary.items():
            if term.lower() in text:
                return f"{definition}\n\nNeed another term defined? Just ask!"
        
        return self._show_all_terms()

    def handle_training_webinar(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle webinar requests"""
        return self._show_webinar_schedule()

    def handle_onboarding_welcome(self, language: str = "en") -> str:
        """Welcome message for new users - ADDED language parameter"""
        return self._get_onboarding_welcome()

    # =========================================================
    # FORMATTING HELPERS (unchanged)
    # =========================================================

    def _format_module_response(self, module_id: str, module: Dict) -> str:
        """Format a module response with sub-modules"""
        response = f"**{module['title']}**\n\n"
        response += f"_{module['description']}_\n\n"
        response += f"⏱️ **Estimated time:** {module['estimated_time']}\n\n"
        
        response += "**📌 Sub-Modules:**\n"
        for sub_id, sub_module in module.get("sub_modules", {}).items():
            # Check if sub_module is a dict with title, or a string
            if isinstance(sub_module, dict) and "title" in sub_module:
                response += f"• **{sub_module['title']}**\n"
            elif isinstance(sub_module, dict) and sub_module.get("sub_modules"):
                # This is a nested sub-module group
                response += f"• **{sub_module.get('title', sub_id.replace('_', ' ').title())}** (group)\n"
            else:
                response += f"• **{sub_id.replace('_', ' ').title()}**\n"
        
        response += f"\n📺 **Video:** {module['video_url']}"
        response += f"\n📄 **Documentation:** {module['doc_url']}"
        
        response += "\n\nWhich sub-module would you like to learn about? Just ask!"
        return response

    def _format_submodule_response(self, module_id: str, sub_id: str, module: Dict, sub_module: Dict) -> str:
        """Format a sub-module response with detailed steps"""
        response = f"**{module['title']} → {sub_module['title']}**\n\n"
        
        response += "**Step-by-Step Guide:**\n"
        for step in sub_module['steps']:
            response += f"{step}\n"
        
        if sub_module.get('tips'):
            response += "\n**💡 Pro Tips:**\n"
            for tip in sub_module['tips']:
                response += f"{tip}\n"
        
        response += f"\n📺 **Video:** {module['video_url']}"
        response += f"\n📄 **Documentation:** {module['doc_url']}"
        
        return response

    def _format_faq_response(self, category: str, faqs: List[Dict]) -> str:
        """Format FAQ response"""
        category_name = category.title()
        response = f"❓ **{category_name} - Frequently Asked Questions**\n\n"
        
        for i, faq in enumerate(faqs, 1):
            response += f"{i}. **Q:** {faq['q']}\n"
            response += f"   **A:** {faq['a']}\n\n"
        
        return response

    def _show_all_modules(self) -> str:
        """Show all available training modules"""
        response = "🎓 **Leysco100 Training Academy**\n\n"
        response += "I can teach you how to use all 19 modules:\n\n"
        
        for module_id, module in self.training_modules.items():
            response += f"**{module['title']}**\n"
            response += f"_{module['description']}_\n"
            sub_count = len(module.get('sub_modules', {}))
            response += f"⏱️ {module['estimated_time']} | 📚 {sub_count} sub-modules\n\n"
        
        response += "Just tell me what you'd like to learn:\n"
        response += "• 'How to use Sales module'\n"
        response += "• 'Teach me Inventory management'\n"
        response += "• 'Show me Production sub-modules'\n"
        response += "• 'Create purchase order guide'\n"
        response += "• 'How to reconcile bank statements'"
        return response

    def _list_all_videos(self) -> str:
        """List all available video tutorials"""
        response = "🎬 **Leysco100 Video Tutorial Library**\n\n"
        
        for topic, url in self.training_videos.items():
            topic_name = topic.replace("_", " ").title()
            response += f"• **{topic_name}:** {url}\n"
        
        response += "\nWhich tutorial would you like to watch? Just say the topic name!"
        return response

    def _show_faq_menu(self) -> str:
        """Show FAQ categories menu"""
        return "❓ **Frequently Asked Questions**\n\n" \
               "Choose a category:\n\n" \
               "1️⃣ **Administration** - Users, settings, approvals\n" \
               "2️⃣ **Sales** - Quotes, orders, invoices\n" \
               "3️⃣ **Purchase** - POs, receipts, vendor invoices\n" \
               "4️⃣ **Inventory** - Items, stock, counting\n" \
               "5️⃣ **Banking** - Payments, reconciliation\n" \
               "6️⃣ **Production** - BOMs, production orders\n" \
               "7️⃣ **Logistics** - Routes, dispatch, tracking\n" \
               "8️⃣ **Gate Pass** - Security, vehicle movement\n" \
               "9️⃣ **Dashboard** - Analytics, KPIs\n\n" \
               "Just say 'inventory FAQ' or ask your specific question!"

    def _show_all_terms(self) -> str:
        """Show all glossary terms"""
        response = "📚 **Leysco100 Glossary of Terms**\n\n"
        
        for term in sorted(self.glossary.keys()):
            response += f"{self.glossary[term]}\n\n"
        
        response += "Which term would you like to learn more about? Just ask!"
        return response

    def _show_webinar_schedule(self) -> str:
        """Show upcoming webinar schedule"""
        response = "🎓 **Upcoming Live Training Webinars**\n\n"
        
        for webinar in self.webinars:
            response += f"**{webinar['topic']}**\n"
            response += f"📅 {webinar['date']} at {webinar['time']}\n"
            response += f"⏱️ {webinar['duration']} with {webinar['instructor']}\n\n"
        
        response += "To register, email training@leysco.com or ask your system administrator."
        return response

    def _get_onboarding_welcome(self) -> str:
        """Welcome message for new users"""
        return """👋 **Karibu Leysco100! Welcome to your new ERP system.**

I'm your personal training assistant, here to help you learn the system step by step.

**🎓 What I Can Teach You:**

📊 **19 Main Modules** with 150+ sub-modules:

• ⚙️ **Administration** - System setup, users, permissions
• 💰 **Financials** - Chart of accounts, taxes, currencies
• 💳 **Banking** - Banks, accounts, payments
• 📦 **Inventory** - Items, warehouses, stock
• 🏭 **Production** - BOMs, orders, costing
• 🛠️ **Resources** - Capacity, availability
• 🔧 **Service** - Contracts, support
• 📤 **Data Imports** - Excel, integrations
• 🔧 **Utilities** - Approvals, monitoring
• 💼 **Sales** - Quotes, orders, invoices
• 📥 **Purchase** - POs, receipts, vendor invoices
• 👥 **Business Partners** - Customers, vendors
• 💳 **Banking Transactions** - Payments, reconciliation
• 📊 **Inventory Transactions** - Movements, reports
• 🛠️ **Resources Mgmt** - Capacity, pricing
• 🚚 **Logistics Hub** - Routes, dispatch, GPS
• 🏭 **Production Ops** - Manufacturing execution
• 🚪 **Gate Pass Mgmt** - Security, vehicle control
• 📊 **Dashboard** - Analytics, insights

**💬 Try Asking:**
• "How do I create a sales order?" - Step-by-step guide
• "Show me inventory sub-modules" - List related topics
• "What does BOM mean?" - Learn terminology
• "Sales module FAQ" - Common questions
• "Show all training modules" - Complete list

What would you like to learn today? I'm here to help! 🚀"""

    def _get_related_modules(self, topic: str) -> str:
        """Get related modules for a topic"""
        relations = {
            "administration": "Users, Permissions, Settings",
            "financials": "Accounting, Taxes, Currencies",
            "banking_master": "Banks, Accounts",
            "inventory_master": "Items, Warehouses, UoM",
            "production_master": "Resources, Routes",
            "resources_master": "Resource Groups, Properties",
            "service": "Contracts",
            "data_imports": "Excel, Integration",
            "utilities": "Approvals, Monitoring",
            "sales": "Quotes, Orders, Invoices",
            "purchase": "POs, Receipts, Invoices",
            "bp": "Customers, Vendors",
            "banking_transactions": "Payments, Reconciliation",
            "inventory_transactions": "Movements, Reports",
            "resources": "Capacity, Pricing",
            "logistics": "Routes, Dispatch, GPS",
            "production": "BOMs, Orders, Costing",
            "gatepass": "Security, Vehicle Movement",
            "dashboard": "Analytics, KPIs"
        }
        return relations.get(topic, "Various related modules")