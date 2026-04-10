# Documentation Writing Stage

Your task is to write or update documentation based on the issue description. Follow this structured approach to ensure high-quality, consistent documentation.

## Step 1: Understand the Scope

Read the issue description carefully. Identify:
- What documentation needs to be created or updated
- The target audience (users, developers, operators)
- Any specific sections or files mentioned

## Step 2: Study Existing Documentation

Before writing, examine existing docs to understand the project's style:

1. List documentation files: `find docs -name "*.md" 2>/dev/null | head -20`
2. Read 2-3 relevant existing docs to understand:
   - Tone and voice (professional, concise, friendly)
   - Heading structure and depth
   - Code block formatting and language tags
   - Use of lists, tables, and callouts
   - File naming conventions

## Step 3: Plan Your Changes

Create a brief outline of what you'll write:
- Main sections and their purpose
- Code examples needed
- Links to related docs or external resources

Do not start writing until you have this outline.

## Step 4: Write the Documentation

Follow these style guidelines:

- **Clear titles**: Use descriptive H1 titles that explain the page's purpose
- **Progressive disclosure**: Start with a summary, then dive into details
- **Code examples**: Include working, tested code snippets with language tags
- **Cross-references**: Link to related documentation where relevant
- **Formatting**: Use backticks for inline code, fenced blocks for multi-line
- **Consistency**: Match the tone and structure of existing docs

## Step 5: Validate Your Work

Before submitting:
- Review for clarity, accuracy, and completeness
- Check all code examples are syntactically correct
- Verify all internal links work
- Ensure no duplicate content exists elsewhere

## Step 6: Create PR

1. Create a feature branch: `git checkout -b docs/{issue-branch}`
2. Commit with a clear message: "docs: add [topic] documentation"
3. Push the branch
4. Open a PR/MR:
   ```bash
   # GitHub
   gh pr create --title "docs: ..." --body "..."

   # GitLab
   glab mr create --title "docs: ..." --description "..."
   ```
   Include:
   - Clear title prefixed with "docs:"
   - Brief description of changes
   - Link to the Linear issue

Mark the task complete when the PR/MR is open and the Linear issue is moved to the review state.
