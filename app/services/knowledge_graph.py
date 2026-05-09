"""
app/services/knowledge_graph.py
================================
Knowledge Graph Service
Maps relationships between products, customers, and warehouses.

FEATURES:
- Product relationships (similar, substitute, complement)
- Customer purchase patterns
- Recommendation queries
- Graph-based reasoning
"""

import logging
import networkx as nx
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass
import json

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# Try to import Neo4j for production graph database
try:
    from neo4j import GraphDatabase, AsyncGraphDatabase
    NEO4J_AVAILABLE = True
    logger.info("✅ Neo4j driver available")
except ImportError:
    NEO4J_AVAILABLE = False
    logger.warning("Neo4j not installed. Using NetworkX in-memory graph.")


@dataclass
class GraphRelationship:
    """Represents a relationship in the knowledge graph"""
    source: str
    target: str
    relationship_type: str
    weight: float
    metadata: Dict[str, Any]


class KnowledgeGraphService:
    """
    Knowledge Graph for product and customer relationships.
    Uses NetworkX in-memory (fallback) or Neo4j (production).
    """
    
    # Relationship types
    REL_BUYS = "BUYS"
    REL_SIMILAR_TO = "SIMILAR_TO"
    REL_SUBSTITUTE_FOR = "SUBSTITUTE_FOR"
    REL_COMPLEMENT_TO = "COMPLEMENT_TO"
    REL_STORED_IN = "STORED_IN"
    REL_BELONGS_TO = "BELONGS_TO"
    REL_RECOMMENDED_WITH = "RECOMMENDED_WITH"
    
    def __init__(self):
        self.cache = get_cache_service()
        self._graph = None
        self._neo4j_driver = None
        self._init_graph()
    
    def _init_graph(self):
        """Initialize graph (NetworkX fallback)."""
        self._graph = nx.DiGraph()
        logger.info("📊 Knowledge Graph initialized (NetworkX)")
    
    # =========================================================
    # NEO4J CONNECTION (Optional)
    # =========================================================
    
    def connect_neo4j(self, uri: str, user: str, password: str):
        """Connect to Neo4j database for production use."""
        if not NEO4J_AVAILABLE:
            logger.warning("Neo4j not available. Install with: pip install neo4j")
            return
        
        try:
            self._neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
            logger.info(f"✅ Connected to Neo4j at {uri}")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
    
    async def close(self):
        """Close Neo4j connection."""
        if self._neo4j_driver:
            await self._neo4j_driver.close()
    
    # =========================================================
    # GRAPH POPULATION
    # =========================================================
    
    async def add_product(self, product_code: str, product_name: str, category: str = None):
        """Add a product node to the graph."""
        self._graph.add_node(
            f"product:{product_code}",
            type="product",
            code=product_code,
            name=product_name,
            category=category
        )
        logger.debug(f"📦 Added product: {product_name} ({product_code})")
    
    async def add_customer(self, customer_code: str, customer_name: str):
        """Add a customer node to the graph."""
        self._graph.add_node(
            f"customer:{customer_code}",
            type="customer",
            code=customer_code,
            name=customer_name
        )
        logger.debug(f"👤 Added customer: {customer_name} ({customer_code})")
    
    async def add_warehouse(self, warehouse_code: str, warehouse_name: str):
        """Add a warehouse node to the graph."""
        self._graph.add_node(
            f"warehouse:{warehouse_code}",
            type="warehouse",
            code=warehouse_code,
            name=warehouse_name
        )
        logger.debug(f"🏭 Added warehouse: {warehouse_name} ({warehouse_code})")
    
    async def add_category(self, category_code: str, category_name: str):
        """Add a category node to the graph."""
        self._graph.add_node(
            f"category:{category_code}",
            type="category",
            code=category_code,
            name=category_name
        )
    
    # =========================================================
    # RELATIONSHIP ADDITION
    # =========================================================
    
    async def add_buy_relationship(
        self,
        customer_code: str,
        product_code: str,
        quantity: float,
        total_value: float,
        order_date: str
    ):
        """Add a BUYS relationship between customer and product."""
        source = f"customer:{customer_code}"
        target = f"product:{product_code}"
        
        # Update or create relationship with aggregated weight
        if self._graph.has_edge(source, target):
            existing = self._graph[source][target]
            new_weight = existing.get("weight", 0) + quantity
            new_total = existing.get("total_value", 0) + total_value
            self._graph[source][target]["weight"] = new_weight
            self._graph[source][target]["total_value"] = new_total
            self._graph[source][target]["purchase_count"] = existing.get("purchase_count", 0) + 1
        else:
            self._graph.add_edge(
                source, target,
                type=self.REL_BUYS,
                weight=quantity,
                total_value=total_value,
                purchase_count=1,
                last_order=order_date
            )
    
    async def add_similar_relationship(
        self,
        product_code_1: str,
        product_code_2: str,
        similarity_score: float,
        reason: str = None
    ):
        """Add a SIMILAR_TO relationship between two products."""
        if product_code_1 == product_code_2:
            return
        
        source = f"product:{product_code_1}"
        target = f"product:{product_code_2}"
        
        self._graph.add_edge(
            source, target,
            type=self.REL_SIMILAR_TO,
            weight=similarity_score,
            reason=reason or "based on category and purchase patterns"
        )
    
    async def add_substitute_relationship(
        self,
        product_code_1: str,
        product_code_2: str,
        substitution_score: float
    ):
        """Add a SUBSTITUTE_FOR relationship (product can replace another)."""
        if product_code_1 == product_code_2:
            return
        
        source = f"product:{product_code_1}"
        target = f"product:{product_code_2}"
        
        self._graph.add_edge(
            source, target,
            type=self.REL_SUBSTITUTE_FOR,
            weight=substitution_score
        )
    
    async def add_complement_relationship(
        self,
        product_code_1: str,
        product_code_2: str,
        complement_score: float
    ):
        """Add a COMPLEMENT_TO relationship (products often bought together)."""
        if product_code_1 == product_code_2:
            return
        
        source = f"product:{product_code_1}"
        target = f"product:{product_code_2}"
        
        self._graph.add_edge(
            source, target,
            type=self.REL_COMPLEMENT_TO,
            weight=complement_score
        )
    
    async def add_warehouse_relationship(
        self,
        product_code: str,
        warehouse_code: str,
        quantity: float
    ):
        """Add a STORED_IN relationship between product and warehouse."""
        source = f"product:{product_code}"
        target = f"warehouse:{warehouse_code}"
        
        self._graph.add_edge(
            source, target,
            type=self.REL_STORED_IN,
            weight=quantity
        )
    
    # =========================================================
    # GRAPH QUERIES
    # =========================================================
    
    async def get_cross_sell_recommendations(
        self,
        product_code: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Find products frequently bought together with this product.
        Uses graph traversal: Product → [customers who bought it] → [other products they bought]
        """
        recommendations = []
        
        product_node = f"product:{product_code}"
        
        if product_node not in self._graph:
            return recommendations
        
        # Find all customers who bought this product
        customers = []
        for neighbor in self._graph.predecessors(product_node):
            if neighbor.startswith("customer:"):
                customers.append(neighbor)
        
        if not customers:
            return recommendations
        
        # Find other products these customers bought
        product_scores = defaultdict(float)
        
        for customer in customers:
            for neighbor in self._graph.successors(customer):
                if neighbor.startswith("product:") and neighbor != product_node:
                    # Get weight (quantity purchased)
                    edge_data = self._graph[customer][neighbor]
                    score = edge_data.get("weight", 1)
                    product_scores[neighbor] += score
        
        # Sort by score and format
        for product, score in sorted(product_scores.items(), key=lambda x: x[1], reverse=True)[:limit]:
            product_data = self._graph.nodes[product]
            recommendations.append({
                "product_code": product.replace("product:", ""),
                "product_name": product_data.get("name", "Unknown"),
                "co_purchase_score": round(score, 2),
                "relationship_type": "cross_sell"
            })
        
        return recommendations
    
    async def get_upsell_recommendations(
        self,
        product_code: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Find higher-value alternatives or upgrades.
        """
        recommendations = []
        
        product_node = f"product:{product_code}"
        
        if product_node not in self._graph:
            return recommendations
        
        # Find similar or substitute products
        for neighbor in self._graph.successors(product_node):
            if neighbor.startswith("product:"):
                edge_data = self._graph[product_node][neighbor]
                rel_type = edge_data.get("type")
                
                if rel_type in [self.REL_SIMILAR_TO, self.REL_SUBSTITUTE_FOR]:
                    product_data = self._graph.nodes[neighbor]
                    recommendations.append({
                        "product_code": neighbor.replace("product:", ""),
                        "product_name": product_data.get("name", "Unknown"),
                        "similarity_score": edge_data.get("weight", 0.5),
                        "relationship_type": rel_type.lower()
                    })
        
        # Sort by similarity score
        recommendations.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
        
        return recommendations[:limit]
    
    async def get_customer_purchase_pattern(
        self,
        customer_code: str
    ) -> Dict:
        """
        Analyze a customer's purchase pattern.
        """
        customer_node = f"customer:{customer_code}"
        
        if customer_node not in self._graph:
            return {
                "customer_code": customer_code,
                "purchased_products": [],
                "total_spent": 0,
                "favorite_category": None,
                "recommendations": []
            }
        
        purchased_products = []
        total_spent = 0
        categories = defaultdict(float)
        
        for neighbor in self._graph.successors(customer_node):
            if neighbor.startswith("product:"):
                edge_data = self._graph[customer_node][neighbor]
                product_data = self._graph.nodes[neighbor]
                
                purchased_products.append({
                    "product_code": neighbor.replace("product:", ""),
                    "product_name": product_data.get("name", "Unknown"),
                    "quantity": edge_data.get("weight", 0),
                    "total_value": edge_data.get("total_value", 0),
                    "purchase_count": edge_data.get("purchase_count", 1)
                })
                
                total_spent += edge_data.get("total_value", 0)
                
                category = product_data.get("category")
                if category:
                    categories[category] += edge_data.get("total_value", 0)
        
        # Determine favorite category
        favorite_category = max(categories.items(), key=lambda x: x[1])[0] if categories else None
        
        # Get recommendations based on purchase patterns
        recommendations = await self._get_customer_recommendations(customer_code, purchased_products)
        
        return {
            "customer_code": customer_code,
            "purchased_products": purchased_products,
            "total_spent": round(total_spent, 2),
            "favorite_category": favorite_category,
            "unique_products": len(purchased_products),
            "recommendations": recommendations
        }
    
    async def _get_customer_recommendations(
        self,
        customer_code: str,
        purchased_products: List[Dict]
    ) -> List[Dict]:
        """Generate recommendations for a customer based on purchase history."""
        recommendations = []
        product_scores = defaultdict(float)
        
        for purchased in purchased_products:
            product_code = purchased["product_code"]
            
            # Get cross-sell recommendations for purchased products
            cross_sell = await self.get_cross_sell_recommendations(product_code, limit=10)
            
            for rec in cross_sell:
                # Weight by purchase quantity
                score = rec["co_purchase_score"] * (purchased.get("quantity", 1) / 10)
                product_scores[rec["product_code"]] += score
        
        # Sort and format
        for product_code, score in sorted(product_scores.items(), key=lambda x: x[1], reverse=True)[:10]:
            if product_code not in [p["product_code"] for p in purchased_products]:
                product_node = f"product:{product_code}"
                if product_node in self._graph:
                    product_data = self._graph.nodes[product_node]
                    recommendations.append({
                        "product_code": product_code,
                        "product_name": product_data.get("name", "Unknown"),
                        "recommendation_score": round(score, 2),
                        "reason": "Customers with similar purchase patterns bought this"
                    })
        
        return recommendations[:5]
    
    async def find_substitutes(
        self,
        product_code: str,
        limit: int = 5
    ) -> List[Dict]:
        """Find substitute products."""
        substitutes = []
        
        product_node = f"product:{product_code}"
        
        if product_node not in self._graph:
            return substitutes
        
        for neighbor in self._graph.successors(product_node):
            if neighbor.startswith("product:"):
                edge_data = self._graph[product_node][neighbor]
                if edge_data.get("type") == self.REL_SUBSTITUTE_FOR:
                    product_data = self._graph.nodes[neighbor]
                    substitutes.append({
                        "product_code": neighbor.replace("product:", ""),
                        "product_name": product_data.get("name", "Unknown"),
                        "substitution_score": edge_data.get("weight", 0.5)
                    })
        
        substitutes.sort(key=lambda x: x["substitution_score"], reverse=True)
        return substitutes[:limit]
    
    async def find_complements(
        self,
        product_code: str,
        limit: int = 5
    ) -> List[Dict]:
        """Find complementary products (often bought together)."""
        complements = []
        
        product_node = f"product:{product_code}"
        
        if product_node not in self._graph:
            return complements
        
        for neighbor in self._graph.successors(product_node):
            if neighbor.startswith("product:"):
                edge_data = self._graph[product_node][neighbor]
                if edge_data.get("type") == self.REL_COMPLEMENT_TO:
                    product_data = self._graph.nodes[neighbor]
                    complements.append({
                        "product_code": neighbor.replace("product:", ""),
                        "product_name": product_data.get("name", "Unknown"),
                        "complement_score": edge_data.get("weight", 0.5)
                    })
        
        # Also get cross-sell recommendations as complements
        cross_sell = await self.get_cross_sell_recommendations(product_code, limit)
        for cs in cross_sell:
            if cs not in complements:
                complements.append(cs)
        
        complements.sort(key=lambda x: x.get("complement_score", 0), reverse=True)
        return complements[:limit]
    
    # =========================================================
    # GRAPH BUILDING FROM DATA
    # =========================================================
    
    async def build_from_sales_data(
        self,
        orders: List[Dict],
        items: List[Dict],
        customers: List[Dict],
        warehouses: List[Dict] = None
    ):
        """
        Build knowledge graph from sales data.
        
        Args:
            orders: List of orders with items
            items: List of products
            customers: List of customers
            warehouses: List of warehouses (optional)
        """
        logger.info("🏗️ Building knowledge graph from sales data...")
        
        # Add products
        for item in items:
            await self.add_product(
                product_code=item.get("ItemCode"),
                product_name=item.get("ItemName"),
                category=item.get("ItmsGrpNam")
            )
        
        # Add customers
        for customer in customers:
            await self.add_customer(
                customer_code=customer.get("CardCode"),
                customer_name=customer.get("CardName")
            )
        
        # Add warehouses
        if warehouses:
            for warehouse in warehouses:
                await self.add_warehouse(
                    warehouse_code=warehouse.get("WhsCode"),
                    warehouse_name=warehouse.get("WhsName")
                )
        
        # Add purchase relationships from orders
        product_pairs = defaultdict(int)
        
        for order in orders:
            customer_code = order.get("CardCode")
            items_in_order = order.get("items", [])
            
            # Track items in this order for co-purchase analysis
            order_products = []
            
            for item in items_in_order:
                product_code = item.get("ItemCode")
                quantity = item.get("Quantity", 0)
                price = item.get("Price", 0)
                total_value = quantity * price
                
                await self.add_buy_relationship(
                    customer_code=customer_code,
                    product_code=product_code,
                    quantity=quantity,
                    total_value=total_value,
                    order_date=order.get("DocDate", "")
                )
                
                order_products.append(product_code)
            
            # Track co-purchases for complement relationships
            for i, p1 in enumerate(order_products):
                for p2 in order_products[i+1:]:
                    pair = tuple(sorted([p1, p2]))
                    product_pairs[pair] += 1
        
        # Build complement relationships from co-purchase patterns
        min_co_purchase = 2
        for (p1, p2), count in product_pairs.items():
            if count >= min_co_purchase:
                # Calculate complement score (normalized)
                score = min(1.0, count / 10)
                await self.add_complement_relationship(p1, p2, score)
                await self.add_complement_relationship(p2, p1, score)
        
        # Build similar relationships based on categories
        products_by_category = defaultdict(list)
        for item in items:
            category = item.get("ItmsGrpNam")
            code = item.get("ItemCode")
            if category and code:
                products_by_category[category].append(code)
        
        for category, product_codes in products_by_category.items():
            for i, p1 in enumerate(product_codes):
                for p2 in product_codes[i+1:]:
                    await self.add_similar_relationship(p1, p2, 0.7, f"Same category: {category}")
                    await self.add_similar_relationship(p2, p1, 0.7, f"Same category: {category}")
        
        logger.info(f"✅ Knowledge graph built with {self._graph.number_of_nodes()} nodes and {self._graph.number_of_edges()} edges")
    
    # =========================================================
    # UTILITY METHODS
    # =========================================================
    
    def get_graph_stats(self) -> Dict:
        """Get statistics about the knowledge graph."""
        return {
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
            "node_types": {
                "products": len([n for n in self._graph.nodes if n.startswith("product:")]),
                "customers": len([n for n in self._graph.nodes if n.startswith("customer:")]),
                "warehouses": len([n for n in self._graph.nodes if n.startswith("warehouse:")])
            },
            "edge_types": {
                "BUYS": len([e for e in self._graph.edges if self._graph.edges[e].get("type") == self.REL_BUYS]),
                "SIMILAR_TO": len([e for e in self._graph.edges if self._graph.edges[e].get("type") == self.REL_SIMILAR_TO]),
                "COMPLEMENT_TO": len([e for e in self._graph.edges if self._graph.edges[e].get("type") == self.REL_COMPLEMENT_TO])
            }
        }
    
    async def export_graph(self, format: str = "json") -> Dict:
        """Export graph for visualization or analysis."""
        nodes = []
        edges = []
        
        for node, attrs in self._graph.nodes(data=True):
            nodes.append({
                "id": node,
                "label": attrs.get("name", node.split(":")[-1]),
                "type": attrs.get("type", "unknown"),
                **attrs
            })
        
        for source, target, attrs in self._graph.edges(data=True):
            edges.append({
                "source": source,
                "target": target,
                "type": attrs.get("type", "unknown"),
                "weight": attrs.get("weight", 1)
            })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "stats": self.get_graph_stats()
        }


# Singleton instance
_knowledge_graph = None


def get_knowledge_graph() -> KnowledgeGraphService:
    """Get or create KnowledgeGraphService singleton."""
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = KnowledgeGraphService()
    return _knowledge_graph