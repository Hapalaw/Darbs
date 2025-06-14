document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const messageForm = document.getElementById('message-form');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const messagesContainer = document.getElementById('messages-container');
    const modelSelect = document.getElementById('model-select');
    const modelStatus = document.getElementById('model-status');
    const newChatBtn = document.getElementById('new-chat-btn');
    const chatIdInput = document.getElementById('chat-id');
    
    // Status flags
    let isGenerating = false;
    let eventSource = null;
    
    // Initialize selectedModel from current selection
    let selectedModel = localStorage.getItem('selectedModel') || '';
    
    // Update model status on page load
    if (selectedModel) {
        modelStatus.textContent = 'Aviable';
        modelStatus.className = 'model-status available';
        validateSendButton();
    }

    // Automatic height change of the text field when entering
    messageInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        
        validateSendButton();
    });

    // Checking the availability of the selected model
	modelSelect.addEventListener('change', function() {
		selectedModel = this.value;
		localStorage.setItem('selectedModel', selectedModel);
        
        if (selectedModel) {
            modelStatus.textContent = 'Aviable';
            modelStatus.className = 'model-status available';
        } else {
            modelStatus.textContent = 'Select a model';
            modelStatus.className = 'model-status';
        }
        
        validateSendButton();
    });

    // Creating new chat
    newChatBtn.addEventListener('click', function() {
        fetch('/create_chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.id) {
				updateChatList();
                window.location.href = `/chat/${data.id}`;
            }
        })
        .catch(error => console.error('Error:', error));
    });

    // Chat deleting
    document.querySelectorAll('.chat-delete').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const chatId = this.getAttribute('data-chat-id');
            
            if (confirm('Are you sure you want to delete this chat?')) {
                fetch(`/delete_chat/${chatId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
						updateChatList();
                        if (chatIdInput.value === chatId) {
                            window.location.href = '/chat';
                        } else {
                            this.parentElement.remove();
                        }
                    }
                })
                .catch(error => console.error('Error:', error));
            }
        });
    });

	// Sending a message
	if (messageForm) {
		messageForm.addEventListener('submit', function(e) {
			e.preventDefault();
			console.log("The form has been submitted, isGenerating:", isGenerating); // Logging on client-side

			if (isGenerating) {
				console.log("Generation stop requested");
				stopGeneration();
				return;
			}

			const chatId = chatIdInput.value;
			const message = messageInput.value.trim();

			if (!chatId || !message || !selectedModel) {
				console.warn("Not enough data to send a message");
				return;
			}

			console.log("Sending a message:", message, "to chat:", chatId, "with model:", selectedModel);
			sendMessage(chatId, message, selectedModel);
		});
	}
    
    // Send button validation function
    function validateSendButton() {
        if (messageInput && sendButton) {
            if (messageInput.value.trim() && selectedModel) {
                sendButton.disabled = false;
            } else {
                sendButton.disabled = true;
            }
        }
    }
    
    // Message sending function
    function sendMessage(chatId, message, model) {
        addMessageToUI('user', message);
        
        messageInput.value = '';
        messageInput.style.height = 'auto';
        validateSendButton();
        
        sendButton.textContent = 'Stop';
        sendButton.classList.add('stop-button');
		sendButton.disabled = false;
        
        // Sending a message to the server
		fetch('/send_message', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ chat_id: chatId, content: message, model: model })
		})
		.then(response => response.json())
		.then(data => {
			if (data.status === 'success') {
				// Updating the chat title in the list
				if (data.updated_chat_title) {
					updateChatTitleInList(chatId, data.updated_chat_title);
				}
				getAssistantResponse(chatId, model);
			}
		})
		.catch(error => {
			console.error('Error:', error);
		});
    }
	
	function updateChatTitleInList(chatId, newTitle) {
		const chatItems = document.querySelectorAll('.chat-item');
		chatItems.forEach(item => {
			if (item.href.endsWith(`/chat/${chatId}`)) {
				const titleElement = item.querySelector('.chat-title');
				titleElement.textContent = newTitle;
				titleElement.classList.add('chat-title-updated');
				setTimeout(() => titleElement.classList.remove('chat-title-updated'), 1000);
			}
		});
	}
	
	function markdownToHtml(text) {
		text = text.replace(/^### (.*$)/gm, '<h3>$1</h3>')
				   .replace(/^## (.*$)/gm, '<h2>$1</h2>')
				   .replace(/^# (.*$)/gm, '<h1>$1</h1>');
		text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
				   .replace(/\*(.*?)\*/g, '<em>$1</em>');
		text = text.replace(/^\s*-\s(.*$)/gm, '<li>$1</li>')
				   .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
		text = text.replace(/\n/g, '<br>');
		return text;
	}
    
	function updateChatList() {
		fetch('/get_chats')
			.then(response => response.json())
			.then(chats => {
				const chatList = document.querySelector('.chats-list');
				chatList.innerHTML = '';
				chats.forEach(chat => {
					const chatLink = document.createElement('a');
					chatLink.href = `/chat/${chat.id}`;
					chatLink.className = `chat-item ${currentChatId == chat.id ? 'active' : ''}`;
					chatLink.innerHTML = `
						<span class="chat-title">${chat.title}</span>
						<span class="chat-delete" data-chat-id="${chat.id}">✖</span>
					`;
					chatList.appendChild(chatLink);

					const deleteButton = chatLink.querySelector('.chat-delete');
					deleteButton.addEventListener('click', function(e) {
						e.preventDefault();
						e.stopPropagation();
						const chatId = this.getAttribute('data-chat-id');
						if (confirm('Are you sure you want to delete this chat?')) {
							fetch(`/delete_chat/${chatId}`, {
								method: 'POST',
								headers: {
									'Content-Type': 'application/json',
								}
							})
							.then(response => response.json())
							.then(data => {
								if (data.success) {
									updateChatList();
									if (currentChatId == chatId) {
										window.location.href = '/chat';
									}
								}
							})
							.catch(error => console.error('Error:', error));
						}
					});
				});
			})
			.catch(error => console.error('Error:', error));
	}
	
	updateChatList();
	
    // The function of receiving the assistant's response
    function getAssistantResponse(chatId, model) {
        const assistantMsgDiv = document.createElement('div');
        assistantMsgDiv.className = 'message assistant-message';
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        
        const assistantAvatar = document.createElement('div');
        assistantAvatar.className = 'assistant-avatar';
        assistantAvatar.textContent = 'A';
        
        avatarDiv.appendChild(assistantAvatar);
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const textDiv = document.createElement('div');
        textDiv.className = 'message-text generating';
        textDiv.id = 'current-response';
        textDiv.textContent = '';
        
        const infoDiv = document.createElement('div');
        infoDiv.className = 'message-info';
        infoDiv.textContent = `Model: ${model}`;
        
        contentDiv.appendChild(textDiv);
        contentDiv.appendChild(infoDiv);
        
        assistantMsgDiv.appendChild(avatarDiv);
        assistantMsgDiv.appendChild(contentDiv);
        
        messagesContainer.appendChild(assistantMsgDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        isGenerating = true;
        
        eventSource = new EventSource(`/get_response?chat_id=${chatId}&model=${model}`);
        
        eventSource.onmessage = function(event) {
			try {
				const data = JSON.parse(event.data);

				if (data.error) {
					console.error('Server error:', data.error);
					textDiv.innerHTML += `<br><span style="color: red;">Error: ${data.error}</span>`;
					completeGeneration();
					return;
				}

				if (data.message_id) {
					textDiv.setAttribute('data-message-id', data.message_id);
					return;
				}

				if (data.content) {
					textDiv.innerHTML += data.content;
					messagesContainer.scrollTop = messagesContainer.scrollHeight;
				}

				if (data.done) {
					completeGeneration();
				}

			} catch (e) {
				console.error('JSON parse error:', e, 'Raw data:', event.data);
				textDiv.innerHTML += `<br><span style="color: red;">Data format error</span>`;
				completeGeneration();
			}
		};
        
        // EventSource error handling
		eventSource.onerror = function(error) {
			console.error('EventSource error:', error);
			const currentResponse = document.getElementById('current-response');
			if (currentResponse) {
				currentResponse.innerHTML += '<span style="color: red;"> [Connection error]</span>';
			}
			completeGeneration();
		};
    }
    
    // Generation completion function
    function completeGeneration() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        
        isGenerating = false;
        const currentResponse = document.getElementById('current-response');
        if (currentResponse) {
            currentResponse.classList.remove('generating');
            currentResponse.removeAttribute('id');
        }
        
        sendButton.textContent = 'Send';
        sendButton.classList.remove('stop-button');
		sendButton.disabled = false;
        
        validateSendButton();
    }
    
    // Stop generation function
	function stopGeneration() {
		console.log("Function stopGeneration() has been called");
		if (eventSource) {
			console.log("Closing the eventSource");
			eventSource.close();
			fetch('/stop_generation', {
				method: 'POST',
				headers: {'Content-Type': 'application/json'},
				body: JSON.stringify({chat_id: chatIdInput.value})
			}).then(response => {
                console.log("Request /stop_generation sent, response:", response.status);
            }).catch(error => {
                console.error("Error when sending a request /stop_generation:", error);
            });
		} else {
            console.warn("EventSource is not active, although stopGeneration() is called");
        }

        isGenerating = false;
        const currentResponse = document.getElementById('current-response');
        if (currentResponse) {
            currentResponse.classList.remove('generating');
            currentResponse.innerHTML += '<span style="color: #5f6368; font-style: italic;"> [Generation stopped]</span>';
            currentResponse.removeAttribute('id');
        }

        sendButton.textContent = 'Send';
        sendButton.classList.remove('stop-button');
        sendButton.disabled = false;

        validateSendButton();
        console.log("Generation stopped, isGenerating:", isGenerating);
    }
    
    // The function of adding a message to the interface
    function addMessageToUI(role, content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}-message`;
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        
        const avatarEl = document.createElement('div');
        avatarEl.className = `${role}-avatar`;
        avatarEl.textContent = role === 'user' ? 'U' : 'A';
        
        avatarDiv.appendChild(avatarEl);
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.innerHTML = markdownToHtml(content);
        
        contentDiv.appendChild(textDiv);
        
        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
	
	// Automatic height change of the text field when entering
    messageInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';

        validateSendButton();
    });

    // Keystroke handler for messageInput
    messageInput.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            if (!sendButton.disabled) {
                messageForm.dispatchEvent(new Event('submit'));
            }
        }
    });
    
    // Check the availability of all models when loading the page
    fetch('/models')
        .then(response => response.json())
		.then(models => {
			modelSelect.innerHTML = '<option value="">Select a model</option>';
			
			if (models?.length > 0) {
				// Auto-selection of a random aviable model at the first opening
				if (!selectedModel) {
					const randomModel = models[Math.floor(Math.random() * models.length)].id;
					selectedModel = randomModel;
					localStorage.setItem('selectedModel', selectedModel);
				}

				models.forEach(model => {
					const option = document.createElement('option');
					option.value = model.id;
					option.textContent = model.id;
					if (model.id === selectedModel) option.selected = true;
					modelSelect.appendChild(option);
				});
				
				modelStatus.textContent = selectedModel ? 'Aviable' : 'Select a model';
			} else {
                modelStatus.textContent = 'There are no available models';
                modelStatus.className = 'model-status unavailable';
            }
        })
	.catch(error => {
				console.error('Error:', error);
				modelStatus.textContent = 'Model loading error';
				modelStatus.className = 'model-status unavailable';
			});
		
		if (messageInput) {
			messageInput.focus();
		}
		
		validateSendButton();
	});