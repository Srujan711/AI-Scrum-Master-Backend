"""
Trello integration client for AI Scrum Master
Handles boards, lists, cards, and workflow automation
"""

import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class TrelloClient:
    """Trello API client for board and card management"""
    
    def __init__(self, api_key: str, token: str):
        self.api_key = api_key
        self.token = token
        self.base_url = "https://api.trello.com/1"
        self.session = requests.Session()
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make authenticated request to Trello API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        # Add authentication to all requests
        params = kwargs.get('params', {})
        params.update({
            'key': self.api_key,
            'token': self.token
        })
        kwargs['params'] = params
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.HTTPError as e:
            logger.error(f"Trello API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Trello request: {e}")
            raise
    
    def get_boards(self, member: str = "me") -> List[Dict[str, Any]]:
        """Get all boards for a member"""
        return self._make_request("GET", f"/members/{member}/boards")
    
    def get_board(self, board_id: str) -> Dict[str, Any]:
        """Get detailed board information"""
        return self._make_request("GET", f"/boards/{board_id}")
    
    def get_lists(self, board_id: str) -> List[Dict[str, Any]]:
        """Get all lists on a board"""
        return self._make_request("GET", f"/boards/{board_id}/lists")
    
    def get_cards(self, board_id: str, list_id: str = None) -> List[Dict[str, Any]]:
        """Get cards from board or specific list"""
        if list_id:
            return self._make_request("GET", f"/lists/{list_id}/cards")
        else:
            return self._make_request("GET", f"/boards/{board_id}/cards")
    
    def get_card(self, card_id: str) -> Dict[str, Any]:
        """Get detailed card information"""
        params = {
            'attachments': 'true',
            'checklists': 'all',
            'members': 'true',
            'actions': 'commentCard,updateCard:closed,updateCard:idList'
        }
        return self._make_request("GET", f"/cards/{card_id}", params=params)
    
    def create_card(self, list_id: str, name: str, desc: str = "", 
                   due_date: str = None, member_ids: List[str] = None) -> Dict[str, Any]:
        """Create a new card"""
        data = {
            'name': name,
            'desc': desc,
            'idList': list_id
        }
        
        if due_date:
            data['due'] = due_date
        
        if member_ids:
            data['idMembers'] = ','.join(member_ids)
        
        return self._make_request("POST", "/cards", params=data)
    
    def update_card(self, card_id: str, **updates) -> Dict[str, Any]:
        """Update card properties"""
        return self._make_request("PUT", f"/cards/{card_id}", params=updates)
    
    def move_card(self, card_id: str, list_id: str) -> Dict[str, Any]:
        """Move card to different list"""
        return self.update_card(card_id, idList=list_id)
    
    def add_comment(self, card_id: str, text: str) -> Dict[str, Any]:
        """Add comment to card"""
        data = {'text': text}
        return self._make_request("POST", f"/cards/{card_id}/actions/comments", params=data)
    
    def get_card_actions(self, card_id: str, filter_types: List[str] = None) -> List[Dict[str, Any]]:
        """Get card activity/actions"""
        params = {}
        if filter_types:
            params['filter'] = ','.join(filter_types)
        
        return self._make_request("GET", f"/cards/{card_id}/actions", params=params)
    
    def get_backlog_cards(self, board_id: str, backlog_list_names: List[str] = None) -> List[Dict[str, Any]]:
        """Get cards from backlog lists"""
        if not backlog_list_names:
            backlog_list_names = ['Backlog', 'Product Backlog', 'To Do']
        
        lists = self.get_lists(board_id)
        backlog_lists = [l for l in lists if l['name'] in backlog_list_names]
        
        backlog_cards = []
        for board_list in backlog_lists:
            cards = self.get_cards(board_id, board_list['id'])
            for card in cards:
                card['list_name'] = board_list['name']
            backlog_cards.extend(cards)
        
        return backlog_cards
    
    def get_sprint_cards(self, board_id: str, sprint_list_names: List[str] = None) -> List[Dict[str, Any]]:
        """Get cards from current sprint lists"""
        if not sprint_list_names:
            sprint_list_names = ['In Progress', 'Doing', 'Sprint', 'Current Sprint']
        
        lists = self.get_lists(board_id)
        sprint_lists = [l for l in lists if l['name'] in sprint_list_names]
        
        sprint_cards = []
        for board_list in sprint_lists:
            cards = self.get_cards(board_id, board_list['id'])
            for card in cards:
                card['list_name'] = board_list['name']
            sprint_cards.extend(cards)
        
        return sprint_cards
    
    def get_done_cards(self, board_id: str, days_back: int = 7) -> List[Dict[str, Any]]:
        """Get recently completed cards"""
        lists = self.get_lists(board_id)
        done_lists = [l for l in lists if 'done' in l['name'].lower() or 'complete' in l['name'].lower()]
        
        done_cards = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        for board_list in done_lists:
            cards = self.get_cards(board_id, board_list['id'])
            for card in cards:
                # Check when card was moved to this list
                actions = self.get_card_actions(card['id'], ['updateCard:idList'])
                for action in actions:
                    if action['data']['listAfter']['id'] == board_list['id']:
                        move_date = datetime.fromisoformat(action['date'].replace('Z', '+00:00'))
                        if move_date >= cutoff_date:
                            card['completed_date'] = action['date']
                            card['list_name'] = board_list['name']
                            done_cards.append(card)
                        break
        
        return done_cards
    
    def analyze_workflow(self, board_id: str) -> Dict[str, Any]:
        """Analyze board workflow and bottlenecks"""
        lists = self.get_lists(board_id)
        cards = self.get_cards(board_id)
        
        list_card_counts = {}
        for board_list in lists:
            list_cards = [c for c in cards if c['idList'] == board_list['id']]
            list_card_counts[board_list['name']] = len(list_cards)
        
        # Identify potential bottlenecks (lists with many cards)
        avg_cards = sum(list_card_counts.values()) / len(list_card_counts) if list_card_counts else 0
        bottlenecks = {name: count for name, count in list_card_counts.items() 
                      if count > avg_cards * 1.5}
        
        return {
            'total_cards': len(cards),
            'lists_card_distribution': list_card_counts,
            'potential_bottlenecks': bottlenecks,
            'workflow_health_score': self._calculate_workflow_health(list_card_counts)
        }
    
    def _calculate_workflow_health(self, list_counts: Dict[str, int]) -> float:
        """Calculate workflow health score (0-1)"""
        if not list_counts:
            return 0.0
        
        # Good workflow should have balanced distribution
        counts = list(list_counts.values())
        avg = sum(counts) / len(counts)
        variance = sum((c - avg) ** 2 for c in counts) / len(counts)
        
        # Lower variance = better health (normalized score)
        max_possible_variance = avg ** 2  # Worst case: all cards in one list
        if max_possible_variance == 0:
            return 1.0
        
        health_score = max(0, 1 - (variance / max_possible_variance))
        return round(health_score, 2)
    
    def detect_duplicate_cards(self, board_id: str, similarity_threshold: float = 0.8) -> List[List[Dict[str, Any]]]:
        """Detect potential duplicate cards using text similarity"""
        cards = self.get_cards(board_id)
        duplicates = []
        
        from difflib import SequenceMatcher
        
        for i, card1 in enumerate(cards):
            for card2 in cards[i+1:]:
                # Compare names
                name_similarity = SequenceMatcher(None, card1['name'].lower(), card2['name'].lower()).ratio()
                
                # Compare descriptions if available
                desc_similarity = 0
                if card1.get('desc') and card2.get('desc'):
                    desc_similarity = SequenceMatcher(None, card1['desc'].lower(), card2['desc'].lower()).ratio()
                
                # Combined similarity score
                combined_similarity = (name_similarity * 0.7) + (desc_similarity * 0.3)
                
                if combined_similarity >= similarity_threshold:
                    duplicates.append([card1, card2])
        
        return duplicates
    
    def get_sprint_summary(self, board_id: str, days_back: int = 14) -> Dict[str, Any]:
        """Generate sprint summary from Trello activity"""
        try:
            done_cards = self.get_done_cards(board_id, days_back)
            sprint_cards = self.get_sprint_cards(board_id)
            workflow_analysis = self.analyze_workflow(board_id)
            
            # Calculate completion rate
            total_sprint_cards = len(sprint_cards) + len(done_cards)
            completion_rate = len(done_cards) / total_sprint_cards if total_sprint_cards > 0 else 0
            
            # Get overdue cards
            overdue_cards = []
            for card in sprint_cards:
                if card.get('due'):
                    due_date = datetime.fromisoformat(card['due'].replace('Z', '+00:00'))
                    if due_date < datetime.now():
                        overdue_cards.append(card)
            
            return {
                'completed_cards': len(done_cards),
                'in_progress_cards': len(sprint_cards),
                'completion_rate': round(completion_rate * 100, 1),
                'overdue_cards': len(overdue_cards),
                'workflow_health': workflow_analysis['workflow_health_score'],
                'bottlenecks': workflow_analysis['potential_bottlenecks'],
                'summary_period_days': days_back
            }
        except Exception as e:
            logger.error(f"Error generating Trello sprint summary: {e}")
            return {}
    
    def create_card_from_discussion(self, list_id: str, discussion_summary: str, 
                                  ai_suggested_title: str = None) -> Dict[str, Any]:
        """Create card from team discussion with AI assistance"""
        title = ai_suggested_title or f"Task from discussion - {datetime.now().strftime('%Y-%m-%d')}"
        
        description = f"""
**Generated from team discussion:**

{discussion_summary}

**Created by:** AI Scrum Master
**Date:** {datetime.now().isoformat()}
        """.strip()
        
        return self.create_card(list_id, title, description)
    
    def add_ai_comment(self, card_id: str, ai_analysis: str, comment_type: str = "analysis") -> Dict[str, Any]:
        """Add AI-generated comment to card"""
        comment_prefix = {
            'analysis': '🤖 **AI Analysis:**',
            'suggestion': '💡 **AI Suggestion:**',
            'update': '📊 **AI Update:**'
        }.get(comment_type, '🤖 **AI Comment:**')
        
        comment_text = f"{comment_prefix}\n\n{ai_analysis}"
        return self.add_comment(card_id, comment_text)


class TrelloWebhookHandler:
    """Handle Trello webhook events"""
    
    def __init__(self, client: TrelloClient):
        self.client = client
    
    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process Trello webhook events"""
        action = payload.get('action', {})
        action_type = action.get('type', '')
        
        handlers = {
            'updateCard': self._handle_card_update,
            'createCard': self._handle_card_create,
            'commentCard': self._handle_card_comment,
            'deleteCard': self._handle_card_delete
        }
        
        handler = handlers.get(action_type)
        if handler:
            return handler(action)
        else:
            logger.info(f"Unhandled Trello action type: {action_type}")
            return {'status': 'ignored', 'action_type': action_type}
    
    def _handle_card_update(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle card update events"""
        data = action.get('data', {})
        card = data.get('card', {})
        
        # Check if card was moved between lists
        list_before = data.get('listBefore')
        list_after = data.get('listAfter')
        
        if list_before and list_after:
            return {
                'event_type': 'card_moved',
                'card_id': card.get('id'),
                'card_name': card.get('name'),
                'from_list': list_before.get('name'),
                'to_list': list_after.get('name'),
                'board_id': data.get('board', {}).get('id')
            }
        
        return {
            'event_type': 'card_updated',
            'card_id': card.get('id'),
            'card_name': card.get('name'),
            'changes': data
        }
    
    def _handle_card_create(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle card creation events"""
        data = action.get('data', {})
        card = data.get('card', {})
        
        return {
            'event_type': 'card_created',
            'card_id': card.get('id'),
            'card_name': card.get('name'),
            'list_id': data.get('list', {}).get('id'),
            'board_id': data.get('board', {}).get('id')
        }
    
    def _handle_card_comment(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle card comment events"""
        data = action.get('data', {})
        card = data.get('card', {})
        
        return {
            'event_type': 'card_commented',
            'card_id': card.get('id'),
            'card_name': card.get('name'),
            'comment_text': data.get('text', ''),
            'member_id': action.get('idMemberCreator')
        }
    
    def _handle_card_delete(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle card deletion events"""
        data = action.get('data', {})
        card = data.get('card', {})
        
        return {
            'event_type': 'card_deleted',
            'card_id': card.get('id'),
            'card_name': card.get('name'),
            'board_id': data.get('board', {}).get('id')
        }