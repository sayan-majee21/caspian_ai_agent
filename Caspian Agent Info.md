# STUDENT RECRUITER PORTFOLIO TRACKER

**Input Info from:**
- GitHub
- Kaggle
- Caspian Connector

## AGENT 1
- Using Gemini Flash that analyzes the entire new github repo once for the first time and updates the information in the dataset.
- On every update/change in the repo (like commit/pull), analyze the change and reflect it accordingly on the database. 
- The agent scans the database to check if a similar suggestion by any recruiter has been posted for that repo. If yes, then the corresponding recruiter will be sent a follow-up mail regarding the new update by the student.
- **RATING AND CLASSIFICATION OF PROJECT** - this will include the creation of several metrics that will further contribute to a final score on whose basis only the high-rated projects will be further be transferred to Agent 2. 

## DATABASE
- Agent 1 will give a short write up on the project and its details. 
- Suggestion Tab updated by recruiter.

## AGENT 2
- First, for the received project - find all the interested recruiters based on the recruiter’s choice filters.
- Customized mails must be created for each recruiter telling the insight of the idea along with the details of the student. 
- A link will be attached granting access to a student’s dashboard, where the recruiter can see his entire portfolio along with some suggestion tabs. (The message to the recruiter must be very simple, just like a notification). 

## CASPIAN CONNECTOR 2
- Sends the mail framed by Agent 2 to the recruiter.
- Reflects the suggestions made by the recruiter to the database.
