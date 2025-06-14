# Jarvis Commands

## Overview
The `commands` directory contains various modules that define the functionalities of Jarvis. Each command is designed to perform specific tasks and interact with the user or external APIs. To use a specific command, there must be a keyword in the instruct you give.

## Commands

### 1. **Calculator Command**
- **Description**: Performs basic arithmetic operations.
- **Usage**: Accepts mathematical expressions and returns the result.
- **Keyword**: `oblicz`

### 2. **Discord Message Command**
- **Description**: Sends messages to specific Discord channels.
- **Usage**: Requires environment variables for channel IDs and interacts with the Discord API.
- **Keyword**: `wyślij wiadomość`

### 3. **Google Command**
- **Description**: Searches Google for user queries.
- **Usage**: Returns search results based on user input.
- **Keyword**: `google`

### 4. **Time Command**
- **Description**: Provides the current time or calculates time differences.
- **Usage**: Useful for scheduling and time-related queries.
- **Keyword**: `godzina`

### 5. **Train Command**
- **Description**: Processes train schedule data.
- **Usage**: Reads data from the `pociagi` directory and provides train-related information.
- **Keyword**: `pociąg`

### 6. **YouTube Command**
- **Description**: Searches YouTube for videos.
- **Usage**: Requires a YouTube API key and returns video search results.
- **Keyword**: `youtube`

## Notes
- Each command is implemented as a separate Python module.
- Commands may require specific environment variables or API keys to function correctly.
- Modify or extend commands as needed to add new functionalities.

## Additional Information
For more details on how to use or extend these commands, refer to the main `README.md` file in the project root.
