

IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RC_COMPLAINT_EXTRACT]') AND type in (N'U'))
DROP TABLE [dbo].[RC_COMPLAINT_EXTRACT]
GO

/****** Object:  Table [dbo].[RC_COMPLAINT_EXTRACT] ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[RC_COMPLAINT_EXTRACT](
	[Extended_Debt_Code] [int] NULL,
	[Client_Code] [nvarchar](100) NULL,
	[Client_Group] [nvarchar](100) NULL,
	[CMP_Complaint_Number] [int] NULL,
	[CMP_Received_Via] [nvarchar](100) NULL,
	[CMP_Enter_date] [datetime] NULL,
	[CMP_Made_Date] [datetime] NULL,
	[CMP_Logged_By] [nvarchar](100) NULL,
	[CMP_Source] [nvarchar](100) NULL,
	[CMP_Issue_1] [nvarchar](1000) NULL,
	[CMP_Sub_Issue_1] [nvarchar](1000) NULL,
	[CMP_Issue_2] [nvarchar](1000) NULL,
	[CMP_Sub_Issue_2] [nvarchar](1000) NULL,
	[CMP_Issue_3] [nvarchar](1000) NULL,
	[CMP_Sub_Issue_3] [nvarchar](1000) NULL,
	[CMP_Details] [nvarchar](max) NULL,
	[CMP_Expected_Outcome] [nvarchar](max) NULL,
	[CMP_Preferred_Contact] [nvarchar](100) NULL,
	[CMP_Action_Taken] [nvarchar](max) NULL,
	[CMP_Warranted] [nvarchar](100) NULL,
	[CMP_Default_Listing_Removed] [nvarchar](100) NULL,
	[CMP_Default_Client] [nvarchar](100) NULL,
	[CMP_Escalate_To] [nvarchar](1000) NULL,
	[CMP_Callback] [nvarchar](1000) NULL,
	[CMP_Reviewed_By] [nvarchar](100) NULL,
	[CMP_Review_Date] [datetime] NULL,
	[CMP_Outcome] [nvarchar](1000) NULL,
	[CMP_Priority] [nvarchar](100) NULL,
	[CMP_Referred_From_AFCA] [nvarchar](100) NULL,
	[CMP_AFCA_Referred_Date] [datetime] NULL,
	[CMP_AFCA_Date_Required] [datetime] NULL,
	[CMP_Status] [nvarchar](100) NULL,
	[CMP_Status_Date] [datetime] NULL,
	[CMP_Info_Requested] [nvarchar](100) NULL,
	[CMP_Info_Sent_Date] [datetime] NULL,
	[CMP_Client_Email_Sent] [nvarchar](100) NULL,
	[CMP_Entity] [nvarchar](100) NULL,
	[CMP_Impact] [nvarchar](100) NULL,
	[CMP_Impact_Details] [nvarchar](max) NULL,
	[CMP_Ownership] [nvarchar](1000) NULL,
	[CMP_Referred_to_Client_Date] [datetime] NULL,
	[CMP_Severity] [nvarchar](100) NULL,
	[Westpac_Action] [nvarchar](1000) NULL,
	[Westpac_Action_Description] [nvarchar](max) NULL,
	[Westpac_Action_Hold_Date] [datetime] NULL,
	[Westpac_Ref_Number] [nvarchar](100) NULL,
	[Afca_Case_Number] [nvarchar](100) NULL,
	[Zendesk_Ticket_Number] [nvarchar](100) NULL,
	[ZID] [nvarchar](100) NULL,
	[Client_Transfer_Date] [datetime] NULL
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
