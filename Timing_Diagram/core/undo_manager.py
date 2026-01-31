import copy
from core.models import Project, Signal

class UndoManager:
    def __init__(self, project):
        self.project = project
        self.undo_stack = []
        self.redo_stack = []
        self.pending_snapshot = None # For Lazy/Grouped Undo
        
    def push_snapshot(self):
        """Captures the CURRENT project state IMMEDIATELY."""
        self.pending_snapshot = None # Clear any pending
        state = copy.deepcopy(self.project.to_dict())
        self.undo_stack.append(state)
        # Clearing redo stack on new branch of history
        self.redo_stack.clear()

    def request_snapshot(self):
        """Captures the current state as Pending, but does not push yet.
           Used before potential edits (FocusIn, DragStart)."""
        if self.pending_snapshot is None:
            self.pending_snapshot = copy.deepcopy(self.project.to_dict())
            
    def commit_snapshot(self):
        """Determines if a pending snapshot should be committed.
           Called when data actually changes."""
        if self.pending_snapshot is not None:
             # Push the PENDING state (the state BEFORE change)
             self.undo_stack.append(self.pending_snapshot)
             self.redo_stack.clear()
             self.pending_snapshot = None
        
    def can_undo(self):
        return len(self.undo_stack) > 0
        
    def can_redo(self):
        return len(self.redo_stack) > 0

    def undo(self):
        self.pending_snapshot = None # Discard pending on undo
        if not self.can_undo(): return False
        
        # 1. Push current state to Redo
        current_state = copy.deepcopy(self.project.to_dict())
        self.redo_stack.append(current_state)
        
        # 2. Pop previous state
        prev_state = self.undo_stack.pop()
        
        # 3. Restore
        self._restore_state(prev_state)
        return True

    def redo(self):
        self.pending_snapshot = None # Discard pending on redo
        if not self.can_redo(): return False
        
        # 1. Push current state to Undo
        current_state = copy.deepcopy(self.project.to_dict())
        self.undo_stack.append(current_state)
        
        # 2. Pop next state
        next_state = self.redo_stack.pop()
        
        # 3. Restore
        self._restore_state(next_state)
        return True
        
    def _restore_state(self, state):
        # Update Project In-Place
        self.project.name = state.get('name', 'Untitled')
        self.project.total_cycles = state.get('total_cycles', 20)
        self.project.cycle_width = state.get('cycle_width', 40)
        
        self.project.signals.clear()
        signals_data = state.get('signals', [])
        for s_data in signals_data:
            self.project.add_signal(Signal.from_dict(s_data))
