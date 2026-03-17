import os
import json
import stripe
import paypalrestsdk
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import sqlite3
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class SubscriptionTier(Enum):
    """Níveis de assinatura"""
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"

@dataclass
class SubscriptionPlan:
    """Plano de assinatura"""
    name: str
    tier: SubscriptionTier
    price_monthly: float
    price_yearly: float
    features: List[str]
    limits: Dict[str, Any]
    stripe_price_id: Optional[str] = None
    paypal_plan_id: Optional[str] = None

class MonetizationSystem:
    """Sistema de monetização e gerenciamento de assinaturas"""
    
    def __init__(self, app=None):
        self.app = app
        self.stripe = None
        self.paypal = None
        self.db_path = 'subscriptions.db'
        
        if app:
            self.init_app(app)
        
        self.init_db()
        self.init_payment_providers()
        self.plans = self._define_plans()
    
    def init_app(self, app):
        """Inicializa com app Flask"""
        # Stripe
        stripe.api_key = app.config.get('STRIPE_SECRET_KEY', os.environ.get('STRIPE_SECRET_KEY'))
        app.config['STRIPE_PUBLISHABLE_KEY'] = app.config.get(
            'STRIPE_PUBLISHABLE_KEY', 
            os.environ.get('STRIPE_PUBLISHABLE_KEY')
        )
        
        # PayPal
        self.paypal_mode = app.config.get('PAYPAL_MODE', 'sandbox')
        paypalrestsdk.configure({
            "mode": self.paypal_mode,
            "client_id": app.config.get('PAYPAL_CLIENT_ID', os.environ.get('PAYPAL_CLIENT_ID')),
            "client_secret": app.config.get('PAYPAL_CLIENT_SECRET', os.environ.get('PAYPAL_CLIENT_SECRET'))
        })
    
    def init_payment_providers(self):
        """Inicializa provedores de pagamento"""
        try:
            # Stripe
            if stripe.api_key:
                self.stripe = stripe
            
            # PayPal
            self.paypal = paypalrestsdk
        except Exception as e:
            logger.error(f"Erro ao inicializar provedores de pagamento: {e}")
    
    def init_db(self):
        """Inicializa banco de dados de assinaturas"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela de planos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscription_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                tier TEXT NOT NULL,
                price_monthly REAL NOT NULL,
                price_yearly REAL NOT NULL,
                features TEXT NOT NULL,
                limits TEXT NOT NULL,
                stripe_price_id TEXT,
                paypal_plan_id TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de assinaturas de usuários
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                stripe_subscription_id TEXT,
                paypal_subscription_id TEXT,
                status TEXT NOT NULL,
                current_period_start TIMESTAMP,
                current_period_end TIMESTAMP,
                cancel_at_period_end BOOLEAN DEFAULT 0,
                trial_end TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (plan_id) REFERENCES subscription_plans (id)
            )
        ''')
        
        # Tabela de uso
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usage_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value INTEGER NOT NULL,
                period_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Tabela de transações
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subscription_id INTEGER,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                payment_method TEXT NOT NULL,
                payment_provider TEXT NOT NULL,
                transaction_id TEXT,
                status TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (subscription_id) REFERENCES user_subscriptions (id)
            )
        ''')
        
        # Tabela de cupons de desconto
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS discount_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                discount_type TEXT NOT NULL, -- 'percentage' or 'fixed'
                discount_value REAL NOT NULL,
                max_uses INTEGER,
                used_count INTEGER DEFAULT 0,
                valid_from TIMESTAMP,
                valid_until TIMESTAMP,
                applies_to_plans TEXT, -- JSON array of plan tiers
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _define_plans(self) -> Dict[str, SubscriptionPlan]:
        """Define os planos de assinatura"""
        return {
            'free': SubscriptionPlan(
                name='Grátis',
                tier=SubscriptionTier.FREE,
                price_monthly=0.0,
                price_yearly=0.0,
                features=[
                    '5 conversões por mês',
                    'PDFs até 10MB',
                    'Áudio em qualidade padrão',
                    'Suporte por email'
                ],
                limits={
                    'conversions_per_month': 5,
                    'max_file_size_mb': 10,
                    'audio_quality': 'standard',
                    'support_level': 'email',
                    'parallel_processing': False,
                    'cloud_storage': False,
                    'advanced_features': False
                }
            ),
            'basic': SubscriptionPlan(
                name='Básico',
                tier=SubscriptionTier.BASIC,
                price_monthly=9.99,
                price_yearly=99.99,
                features=[
                    '50 conversões por mês',
                    'PDFs até 50MB',
                    'Áudio em alta qualidade',
                    'Suporte prioritário',
                    'Processamento paralelo',
                    'Cache inteligente'
                ],
                limits={
                    'conversions_per_month': 50,
                    'max_file_size_mb': 50,
                    'audio_quality': 'high',
                    'support_level': 'priority',
                    'parallel_processing': True,
                    'cloud_storage': True,
                    'cloud_storage_gb': 10,
                    'advanced_features': False
                }
            ),
            'premium': SubscriptionPlan(
                name='Premium',
                tier=SubscriptionTier.PREMIUM,
                price_monthly=19.99,
                price_yearly=199.99,
                features=[
                    'Conversões ilimitadas',
                    'PDFs até 200MB',
                    'Áudio em qualidade máxima',
                    'Suporte dedicado 24/7',
                    'Processamento paralelo avançado',
                    'Cache ilimitado',
                    'Todos os formatos suportados',
                    'Editor WYSIWYG',
                    'Análise avançada com IA',
                    'Vozes personalizadas'
                ],
                limits={
                    'conversions_per_month': float('inf'),
                    'max_file_size_mb': 200,
                    'audio_quality': 'maximum',
                    'support_level': 'dedicated',
                    'parallel_processing': True,
                    'cloud_storage': True,
                    'cloud_storage_gb': 100,
                    'advanced_features': True,
                    'ai_features': True,
                    'custom_voices': True
                }
            ),
            'enterprise': SubscriptionPlan(
                name='Enterprise',
                tier=SubscriptionTier.ENTERPRISE,
                price_monthly=99.99,
                price_yearly=999.99,
                features=[
                    'Tudo do Premium +',
                    'API ilimitada',
                    'Integração personalizada',
                    'SLA garantido',
                    'Treinamento para equipe',
                    'Servidor dedicado',
                    'Multiusuário com controle de acesso',
                    'Relatórios avançados',
                    'Compliance completo (GDPR, LGPD)',
                    'Suporte técnico dedicado'
                ],
                limits={
                    'conversions_per_month': float('inf'),
                    'max_file_size_mb': 1000,
                    'audio_quality': 'maximum',
                    'support_level': 'enterprise',
                    'parallel_processing': True,
                    'cloud_storage': True,
                    'cloud_storage_gb': 1000,
                    'advanced_features': True,
                    'ai_features': True,
                    'custom_voices': True,
                    'api_access': True,
                    'multi_user': True,
                    'sla_guaranteed': True,
                    'custom_integration': True
                }
            )
        }
    
    def create_stripe_checkout_session(self, plan_name: str, user_id: int, success_url: str, cancel_url: str) -> Dict[str, Any]:
        """Cria sessão de checkout Stripe"""
        if not self.stripe:
            return {'error': 'Stripe não configurado'}
        
        plan = self.plans.get(plan_name)
        if not plan:
            return {'error': 'Plano não encontrado'}
        
        try:
            # Criar ou recuperar cliente Stripe
            customer = self._get_or_create_stripe_customer(user_id)
            
            # Criar sessão de checkout
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                mode='subscription',
                customer=customer.id,
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': plan.name,
                            'description': f'Assinatura {plan.name}',
                            'images': ['https://seusite.com/logo.png']
                        },
                        'unit_amount': int(plan.price_monthly * 100), # Converter para centavos
                        'recurring': {
                            'interval': 'month',
                            'interval_count': 1
                        }
                    },
                    'quantity': 1,
                }],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'user_id': user_id,
                    'plan_name': plan_name
                }
            )
            
            return {
                'success': True,
                'session_id': session.id,
                'checkout_url': session.url
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Erro Stripe: {e}")
            return {'error': str(e)}
    
    def create_paypal_subscription(self, plan_name: str, user_id: int, return_url: str, cancel_url: str) -> Dict[str, Any]:
        """Cria assinatura PayPal"""
        if not self.paypal:
            return {'error': 'PayPal não configurado'}
        
        plan = self.plans.get(plan_name)
        if not plan:
            return {'error': 'Plano não encontrado'}
        
        try:
            # Criar plano no PayPal
            paypal_plan = self.paypal.BillingPlan({
                "name": plan.name,
                "description": f"Assinatura {plan.name}",
                "type": "fixed",
                "payment_definitions": [{
                    "name": f"Custo mensal {plan.name}",
                    "type": "REGULAR",
                    "frequency": "Month",
                    "amount": {
                        "value": plan.price_monthly,
                        "currency": "USD"
                    },
                    "cycles": "0"
                }],
                "merchant_preferences": {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                    "auto_bill_amount": "YES",
                    "initial_fail_amount_action": "CONTINUE",
                    "max_fail_attempts": "0"
                }
            })
            
            if paypal_plan.create():
                # Criar assinatura
                agreement = self.paypal.BillingAgreement({
                    "name": f"Assinatura {plan.name}",
                    "description": f"Assinatura mensal do plano {plan.name}",
                    "plan": paypal_plan.id,
                    "payer": {
                        "payment_method": "paypal"
                    }
                })
                
                if agreement.create():
                    approval_url = next(link.href for link in agreement.links if link.rel == "approval_url")
                    
                    return {
                        'success': True,
                        'approval_url': approval_url,
                        'agreement_id': agreement.id
                    }
            
            return {'error': 'Erro ao criar assinatura PayPal'}
            
        except Exception as e:
            logger.error(f"Erro PayPal: {e}")
            return {'error': str(e)}
    
    def handle_stripe_webhook(self, payload: str, sig_header: str) -> Dict[str, Any]:
        """Processa webhook do Stripe"""
        if not self.stripe:
            return {'error': 'Stripe não configurado'}
        
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.app.config['STRIPE_WEBHOOK_SECRET']
            )
        except ValueError as e:
            return {'error': 'Payload inválido'}
        except stripe.error.SignatureVerificationError as e:
            return {'error': 'Assinatura inválida'}
        
        # Processar eventos
        if event['type'] == 'invoice.payment_succeeded':
            self._handle_payment_success(event['data']['object'])
        elif event['type'] == 'customer.subscription.deleted':
            self._handle_subscription_canceled(event['data']['object'])
        elif event['type'] == 'invoice.payment_failed':
            self._handle_payment_failed(event['data']['object'])
        
        return {'success': True, 'processed': True}
    
    def _handle_payment_success(self, invoice):
        """Processa pagamento bem-sucedido"""
        try:
            subscription_id = invoice['subscription']
            customer_id = invoice['customer']
            amount = invoice['amount_paid'] / 100  # Converter de centavos
            
            # Obter informações da assinatura
            subscription = self.stripe.Subscription.retrieve(subscription_id)
            
            # Salvar no banco
            self._save_subscription(
                customer_id=customer_id,
                subscription_id=subscription_id,
                amount=amount,
                payment_method='stripe',
                status='active',
                current_period_start=datetime.fromtimestamp(subscription.current_period_start),
                current_period_end=datetime.fromtimestamp(subscription.current_period_end)
            )
            
        except Exception as e:
            logger.error(f"Erro ao processar pagamento: {e}")
    
    def _save_subscription(self, customer_id: str, subscription_id: str, amount: float, 
                         payment_method: str, status: str, current_period_start, 
                         current_period_end):
        """Salva assinatura no banco"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Obter user_id do customer_id (assumindo que há uma tabela de customers)
        user_id = self._get_user_id_from_stripe_customer(customer_id)
        
        # Obter plan_id
        plan_name = self._get_plan_from_subscription_id(subscription_id)
        plan_id = self._get_plan_id_from_name(plan_name)
        
        cursor.execute('''
            INSERT INTO user_subscriptions (
                user_id, plan_id, stripe_subscription_id, status,
                current_period_start, current_period_end
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, plan_id, subscription_id, status, 
               current_period_start, current_period_end))
        
        # Registrar transação
        cursor.execute('''
            INSERT INTO transactions (
                user_id, subscription_id, amount, payment_method, 
                payment_provider, transaction_id, status, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, cursor.lastrowid, amount, payment_method, 
               'stripe', subscription_id, 'completed', f'Assinatura {plan_name}'))
        
        conn.commit()
        conn.close()
    
    def check_user_limits(self, user_id: int, metric: str) -> Dict[str, Any]:
        """Verifica limites do usuário"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Obter plano atual do usuário
        cursor.execute('''
            SELECT sp.tier, sp.limits FROM user_subscriptions us
            JOIN subscription_plans sp ON us.plan_id = sp.id
            WHERE us.user_id = ? AND us.status = 'active'
            ORDER BY us.created_at DESC
            LIMIT 1
        ''', (user_id,))
        
        result = cursor.fetchone()
        
        if not result:
            # Usuário gratuito
            tier = SubscriptionTier.FREE
            limits = self.plans['free'].limits
        else:
            tier = SubscriptionTier(result[0])
            limits = json.loads(result[1])
        
        # Verificar uso atual
        current_period_start = datetime.now().replace(day=1)
        cursor.execute('''
            SELECT SUM(metric_value) as total_usage FROM usage_tracking
            WHERE user_id = ? AND metric_name = ? AND period_date >= ?
        ''', (user_id, metric, current_period_start.date()))
        
        usage_result = cursor.fetchone()
        current_usage = usage_result[0] if usage_result[0] else 0
        
        limit_value = limits.get(metric, float('inf'))
        
        conn.close()
        
        return {
            'tier': tier.value,
            'current_usage': current_usage,
            'limit': limit_value,
            'remaining': max(0, limit_value - current_usage),
            'is_limited': current_usage >= limit_value
        }
    
    def track_usage(self, user_id: int, metric: str, value: int = 1):
        """Registra uso de métrica"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO usage_tracking (user_id, metric_name, metric_value, period_date)
            VALUES (?, ?, ?, ?)
        ''', (user_id, metric, value, datetime.now().date()))
        
        conn.commit()
        conn.close()
    
    def create_discount_code(self, code: str, discount_type: str, discount_value: float, 
                          max_uses: int = None, valid_days: int = 30, 
                          applies_to_plans: List[str] = None) -> bool:
        """Cria cupom de desconto"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO discount_codes (
                    code, discount_type, discount_value, max_uses, 
                    valid_from, valid_until, applies_to_plans
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                code.upper(), discount_type, discount_value, max_uses,
                datetime.now(), datetime.now() + timedelta(days=valid_days),
                json.dumps(applies_to_plans or [])
            ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Erro ao criar cupom: {e}")
            conn.close()
            return False
    
    def apply_discount_code(self, code: str, plan_name: str) -> Dict[str, Any]:
        """Aplica cupom de desconto a um plano"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM discount_codes 
            WHERE code = ? AND is_active = 1
            AND (valid_until IS NULL OR valid_until > ?)
            AND (max_uses IS NULL OR used_count < max_uses)
        ''', (code.upper(), datetime.now()))
        
        discount = cursor.fetchone()
        
        if not discount:
            return {'valid': False, 'error': 'Cupom inválido ou expirado'}
        
        # Verificar se o cupom se aplica ao plano
        applies_to_plans = json.loads(discount[8]) if discount[8] else []
        if applies_to_plans and plan_name not in applies_to_plans:
            return {'valid': False, 'error': 'Cupom não aplicável a este plano'}
        
        # Calcular desconto
        plan = self.plans.get(plan_name)
        if not plan:
            return {'valid': False, 'error': 'Plano não encontrado'}
        
        original_price = plan.price_monthly
        
        if discount[1] == 'percentage':
            discount_amount = original_price * (discount[2] / 100)
        else:  # fixed
            discount_amount = discount[2]
        
        final_price = max(0, original_price - discount_amount)
        
        # Atualizar contador de usos
        cursor.execute('''
            UPDATE discount_codes SET used_count = used_count + 1 WHERE id = ?
        ''', (discount[0],))
        
        conn.commit()
        conn.close()
        
        return {
            'valid': True,
            'original_price': original_price,
            'discount_amount': discount_amount,
            'final_price': final_price,
            'discount_type': discount[1]
        }

class EnterpriseManager:
    """Gerenciador de funcionalidades Enterprise"""
    
    def __init__(self, db_path: str = 'enterprise.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inicializa banco de dados enterprise"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela de organizações
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                domain TEXT UNIQUE,
                plan_type TEXT NOT NULL DEFAULT 'enterprise',
                max_users INTEGER DEFAULT 100,
                api_rate_limit INTEGER DEFAULT 10000,
                storage_limit_gb INTEGER DEFAULT 1000,
                features TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de usuários organizacionais
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS org_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                permissions TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (org_id) REFERENCES organizations (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Tabela de configurações organizacionais
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS org_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                setting_key TEXT NOT NULL,
                setting_value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (org_id) REFERENCES organizations (id)
            )
        ''')
        
        # Tabela de logs de auditoria organizacional
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS org_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                user_id INTEGER,
                action TEXT NOT NULL,
                resource TEXT,
                ip_address TEXT,
                user_agent TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN,
                details TEXT,
                FOREIGN KEY (org_id) REFERENCES organizations (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_organization(self, name: str, domain: str, admin_user_id: int, 
                          max_users: int = 100, custom_features: Dict = None) -> int:
        """Cria organização enterprise"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Features padrão enterprise
        default_features = {
            'api_access': True,
            'multi_user': True,
            'custom_integration': True,
            'sla_guaranteed': True,
            'dedicated_support': True,
            'advanced_analytics': True,
            'custom_branding': True,
            'ssso_enabled': True
        }
        
        if custom_features:
            default_features.update(custom_features)
        
        cursor.execute('''
            INSERT INTO organizations (
                name, domain, max_users, features, plan_type
            ) VALUES (?, ?, ?, ?, ?)
        ''', (name, domain, max_users, json.dumps(default_features), 'enterprise'))
        
        org_id = cursor.lastrowid
        
        # Adicionar admin como usuário da organização
        cursor.execute('''
            INSERT INTO org_users (
                org_id, user_id, role, permissions
            ) VALUES (?, ?, ?, ?)
        ''', (org_id, admin_user_id, 'admin', json.dumps(['all'])))
        
        conn.commit()
        conn.close()
        
        return org_id
    
    def add_user_to_organization(self, org_id: int, user_id: int, role: str = 'member', 
                             permissions: List[str] = None) -> bool:
        """Adiciona usuário à organização"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO org_users (org_id, user_id, role, permissions)
                VALUES (?, ?, ?, ?)
            ''', (org_id, user_id, role, json.dumps(permissions or [])))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Erro ao adicionar usuário à organização: {e}")
            conn.close()
            return False
    
    def get_organization_stats(self, org_id: int) -> Dict[str, Any]:
        """Obtém estatísticas da organização"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total de usuários
        cursor.execute('''
            SELECT COUNT(*) as total_users FROM org_users WHERE org_id = ? AND is_active = 1
        ''', (org_id,))
        total_users = cursor.fetchone()[0]
        
        # Uso da API no último mês
        one_month_ago = datetime.now() - timedelta(days=30)
        cursor.execute('''
            SELECT COUNT(*) as api_calls FROM org_audit_logs 
            WHERE org_id = ? AND action = 'api_call' 
            AND timestamp >= ?
        ''', (org_id, one_month_ago))
        api_calls = cursor.fetchone()[0]
        
        # Storage utilizado
        cursor.execute('''
            SELECT SUM(file_size) as storage_used FROM books b
            JOIN users u ON b.user_id = u.id
            JOIN org_users ou ON u.id = ou.user_id
            WHERE ou.org_id = ?
        ''', (org_id,))
        storage_result = cursor.fetchone()
        storage_used = storage_result[0] if storage_result[0] else 0
        
        conn.close()
        
        return {
            'total_users': total_users,
            'api_calls_last_30_days': api_calls,
            'storage_used_bytes': storage_used,
            'storage_used_gb': storage_used / (1024**3),
            'active_conversions': self._get_active_conversions(org_id)
        }
    
    def _get_active_conversions(self, org_id: int) -> int:
        """Obtém número de conversões ativas"""
        # Implementar lógica para contar conversões ativas
        # Isso dependeria da sua estrutura de dados de conversões
        return 0

# Instâncias globais
monetization = MonetizationSystem()
enterprise_manager = EnterpriseManager()
