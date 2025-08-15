"""
GitHub integration client for AI Scrum Master
Handles repository data, pull requests, and commit information
"""

import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class GitHubClient:
    """GitHub API client for repository integration"""
    
    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        self.token = token
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'AI-Scrum-Master/1.0'
        })
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make authenticated request to GitHub API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.HTTPError as e:
            logger.error(f"GitHub API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in GitHub request: {e}")
            raise
    
    def get_repository_info(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get basic repository information"""
        return self._make_request("GET", f"/repos/{owner}/{repo}")
    
    def get_pull_requests(self, owner: str, repo: str, state: str = "all", 
                         days_back: int = 30) -> List[Dict[str, Any]]:
        """Get pull requests from the last N days"""
        since_date = (datetime.now() - timedelta(days=days_back)).isoformat()
        
        params = {
            'state': state,
            'since': since_date,
            'sort': 'updated',
            'direction': 'desc',
            'per_page': 100
        }
        
        return self._make_request("GET", f"/repos/{owner}/{repo}/pulls", params=params)
    
    def get_commits(self, owner: str, repo: str, branch: str = "main", 
                   days_back: int = 7) -> List[Dict[str, Any]]:
        """Get recent commits from a branch"""
        since_date = (datetime.now() - timedelta(days=days_back)).isoformat()
        
        params = {
            'sha': branch,
            'since': since_date,
            'per_page': 100
        }
        
        return self._make_request("GET", f"/repos/{owner}/{repo}/commits", params=params)
    
    def get_pr_for_commit(self, owner: str, repo: str, commit_sha: str) -> Optional[Dict[str, Any]]:
        """Find PR associated with a commit"""
        try:
            # Search for PRs that include this commit
            prs = self._make_request("GET", f"/repos/{owner}/{repo}/commits/{commit_sha}/pulls")
            return prs[0] if prs else None
        except Exception as e:
            logger.warning(f"Could not find PR for commit {commit_sha}: {e}")
            return None
    
    def extract_jira_tickets_from_commit(self, commit_message: str) -> List[str]:
        """Extract Jira ticket references from commit messages"""
        import re
        # Common Jira ticket patterns
        patterns = [
            r'[A-Z]+-\d+',  # Standard Jira format
            r'closes?\s+#?([A-Z]+-\d+)',  # "closes PROJ-123"
            r'fixes?\s+#?([A-Z]+-\d+)',   # "fixes PROJ-123"
        ]
        
        tickets = []
        for pattern in patterns:
            matches = re.findall(pattern, commit_message, re.IGNORECASE)
            tickets.extend(matches)
        
        return list(set(tickets))  # Remove duplicates
    
    def get_deployment_info(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """Get recent deployment information"""
        return self._make_request("GET", f"/repos/{owner}/{repo}/deployments")
    
    def get_workflow_runs(self, owner: str, repo: str, days_back: int = 7) -> List[Dict[str, Any]]:
        """Get GitHub Actions workflow runs"""
        try:
            created_date = (datetime.now() - timedelta(days=days_back)).isoformat()
            params = {
                'created': f'>={created_date}',
                'per_page': 50
            }
            
            response = self._make_request("GET", f"/repos/{owner}/{repo}/actions/runs", params=params)
            return response.get('workflow_runs', [])
        except Exception as e:
            logger.warning(f"Could not get workflow runs: {e}")
            return []
    
    def get_sprint_summary(self, owner: str, repo: str, days_back: int = 14) -> Dict[str, Any]:
        """Generate a sprint summary from GitHub activity"""
        try:
            commits = self.get_commits(owner, repo, days_back=days_back)
            prs = self.get_pull_requests(owner, repo, state="all", days_back=days_back)
            workflows = self.get_workflow_runs(owner, repo, days_back=days_back)
            
            # Extract Jira tickets from commits
            jira_tickets = []
            for commit in commits:
                tickets = self.extract_jira_tickets_from_commit(commit['commit']['message'])
                jira_tickets.extend(tickets)
            
            # Analyze PR status
            merged_prs = [pr for pr in prs if pr.get('merged_at')]
            open_prs = [pr for pr in prs if pr['state'] == 'open']
            
            # Analyze workflow success rate
            successful_workflows = [w for w in workflows if w['conclusion'] == 'success']
            failed_workflows = [w for w in workflows if w['conclusion'] == 'failure']
            
            return {
                'commits_count': len(commits),
                'jira_tickets_referenced': list(set(jira_tickets)),
                'prs_merged': len(merged_prs),
                'prs_open': len(open_prs),
                'workflow_success_rate': len(successful_workflows) / len(workflows) if workflows else 0,
                'failed_workflows': len(failed_workflows),
                'top_contributors': self._get_top_contributors(commits),
                'summary_period_days': days_back
            }
        except Exception as e:
            logger.error(f"Error generating GitHub sprint summary: {e}")
            return {}
    
    def _get_top_contributors(self, commits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get top contributors from commits"""
        contributors = {}
        
        for commit in commits:
            author = commit['commit']['author']['name']
            if author in contributors:
                contributors[author] += 1
            else:
                contributors[author] = 1
        
        # Sort by commit count and return top 5
        sorted_contributors = sorted(contributors.items(), key=lambda x: x[1], reverse=True)
        return [{'name': name, 'commits': count} for name, count in sorted_contributors[:5]]
    
    def create_issue_from_discussion(self, owner: str, repo: str, title: str, 
                                   body: str, labels: List[str] = None) -> Dict[str, Any]:
        """Create GitHub issue from team discussion"""
        data = {
            'title': title,
            'body': body,
            'labels': labels or []
        }
        
        return self._make_request("POST", f"/repos/{owner}/{repo}/issues", json=data)
    
    def add_comment_to_pr(self, owner: str, repo: str, pr_number: int, 
                         comment: str) -> Dict[str, Any]:
        """Add AI-generated comment to a PR"""
        data = {'body': comment}
        return self._make_request("POST", f"/repos/{owner}/{repo}/issues/{pr_number}/comments", json=data)


class GitHubWebhookHandler:
    """Handle GitHub webhook events for real-time updates"""
    
    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key
    
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook signature"""
        if not self.secret_key:
            return True  # Skip verification if no secret configured
        
        import hmac
        import hashlib
        
        expected_signature = hmac.new(
            self.secret_key.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(f"sha256={expected_signature}", signature)
    
    def handle_webhook(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process GitHub webhook events"""
        handlers = {
            'push': self._handle_push_event,
            'pull_request': self._handle_pr_event,
            'issues': self._handle_issue_event,
            'workflow_run': self._handle_workflow_event
        }
        
        handler = handlers.get(event_type)
        if handler:
            return handler(payload)
        else:
            logger.info(f"Unhandled GitHub event type: {event_type}")
            return {'status': 'ignored', 'event_type': event_type}
    
    def _handle_push_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle push events"""
        commits = payload.get('commits', [])
        branch = payload.get('ref', '').replace('refs/heads/', '')
        
        # Extract Jira tickets from commit messages
        jira_tickets = []
        for commit in commits:
            client = GitHubClient("")  # Temporary instance for utility method
            tickets = client.extract_jira_tickets_from_commit(commit['message'])
            jira_tickets.extend(tickets)
        
        return {
            'event_type': 'push',
            'branch': branch,
            'commits_count': len(commits),
            'jira_tickets': list(set(jira_tickets)),
            'repository': payload['repository']['full_name']
        }
    
    def _handle_pr_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle pull request events"""
        action = payload['action']
        pr = payload['pull_request']
        
        return {
            'event_type': 'pull_request',
            'action': action,
            'pr_number': pr['number'],
            'title': pr['title'],
            'state': pr['state'],
            'merged': pr.get('merged', False),
            'repository': payload['repository']['full_name']
        }
    
    def _handle_issue_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle issue events"""
        action = payload['action']
        issue = payload['issue']
        
        return {
            'event_type': 'issues',
            'action': action,
            'issue_number': issue['number'],
            'title': issue['title'],
            'state': issue['state'],
            'repository': payload['repository']['full_name']
        }
    
    def _handle_workflow_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle workflow run events"""
        workflow_run = payload['workflow_run']
        
        return {
            'event_type': 'workflow_run',
            'conclusion': workflow_run['conclusion'],
            'status': workflow_run['status'],
            'workflow_name': workflow_run['name'],
            'branch': workflow_run['head_branch'],
            'repository': payload['repository']['full_name']
        }