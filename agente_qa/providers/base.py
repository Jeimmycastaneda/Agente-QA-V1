from abc import ABC, abstractmethod

class QAProvider(ABC):
    @abstractmethod
    def generate(self, prompt_text, source_content, **kwargs):
        raise NotImplementedError
